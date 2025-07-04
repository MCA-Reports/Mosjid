from flask import Flask, render_template, request, redirect, session, jsonify
from flask_pymongo import PyMongo
from datetime import datetime
import certifi
import re
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key-for-dev-only')

# Use TLS CA Bundle to avoid SSL handshake issues
ca = certifi.where()
app.config["MONGO_URI"] = os.getenv("mongodb+srv://bdkz:bdkz2025@cluster0.yc3hbgc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0-shard-0&ssl=true&ssl_ca_certs=")
app.config["MONGO_TLS_CA_FILE"] = ca

mongo = PyMongo(app)

users_collection = mongo.db.users
members_collection = mongo.db.members
contributions_collection = mongo.db.contributions


def valid_mobile(mobile):
    return re.match(r'^\+?[\d\s()-]{10,15}$', mobile)


def initialize_admin():
    """Create admin user if not exists"""
    if not users_collection.find_one({"username": "admin"}):
        admin_password = os.getenv('ADMIN_INITIAL_PASSWORD', 'Admin@123')
        users_collection.insert_one({
            "username": "admin",
            "password": admin_password,
            "role": "admin",
            "created_at": datetime.utcnow()
        })
        print(f"✅ Admin created: admin / {admin_password}")


def initialize_indexes():
    """Initialize necessary indexes"""
    try:
        contributions_collection.create_index(
            [("member_id", 1), ("month", 1), ("year", 1)],
            unique=True,
            partialFilterExpression={
                "member_id": {"$type": "int"},
                "month": {"$type": "int"},
                "year": {"$type": "int"}
            },
            name="unique_member_month_year"
        )
        print("✅ Index created: unique_member_month_year")
    except Exception as e:
        print(f"⚠️ Index creation failed: {str(e)}")


with app.app_context():
    initialize_admin()
    initialize_indexes()


@app.route('/')
def home():
    return render_template('login.html')


@app.route('/register')
def register_page():
    return render_template('register.html')


@app.route('/member')
def member_page():
    if 'username' not in session or session.get('role') != 'member':
        return redirect('/')
    return render_template('member_dashboard.html', name=session['username'])


@app.route('/admin')
def admin_page():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect('/')
    return render_template('admin_dashboard.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"detail": "Username and password required"}), 400

    try:
        if data['username'] == "admin":
            admin = users_collection.find_one({"username": "admin"})
            if not admin or admin['password'] != data['password']:
                return jsonify({"detail": "Invalid admin credentials"}), 401

            session['username'] = 'admin'
            session['role'] = 'admin'
            return jsonify({
                "message": "Admin logged in",
                "is_admin": True,
                "username": "admin"
            })

        member = members_collection.find_one({"mobile_no": data['username']})
        if not member or member.get('password') != data['password']:
            return jsonify({"detail": "Invalid member credentials"}), 401

        session['username'] = member['first_name']
        session['role'] = 'member'
        session['member_id'] = member['member_id']
        return jsonify({
            "message": "Member logged in",
            "is_admin": False,
            "username": member['first_name']
        })

    except Exception as e:
        return jsonify({"detail": f"Login error: {str(e)}"}), 500


@app.route('/api/members', methods=['POST'])
def create_member():
    data = request.json
    required_fields = ['first_name', 'last_name', 'mobile_no', 'password']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({"detail": f"{field.replace('_', ' ').title()} is required"}), 400

    if not valid_mobile(data['mobile_no']):
        return jsonify({"detail": "Invalid mobile number format"}), 400

    if members_collection.find_one({"mobile_no": data['mobile_no']}):
        return jsonify({"detail": "Mobile number already registered"}), 400

    counter = mongo.db.counters.find_one_and_update(
        {"_id": "member_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    member_id = counter['seq']

    member_data = {
        "member_id": member_id,
        "first_name": data['first_name'],
        "last_name": data['last_name'],
        "mobile_no": data['mobile_no'],
        "password": data['password'],
        "city": data.get('city', ''),
        "fixed_amount": float(data.get('fixed_amount', 0)),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    members_collection.insert_one(member_data)
    return jsonify({
        "message": "Member created successfully",
        "member_id": member_id
    }), 201


@app.route('/api/members', methods=['GET'])
def get_members():
    members = list(members_collection.find({}, {"_id": 0, "password": 0}))
    return jsonify(members), 200


@app.route('/api/contributions', methods=['POST'])
def create_contribution():
    data = request.json
    required_fields = ['amount', 'payment_method', 'purpose', 'member_id']
    for field in required_fields:
        if field not in data or data[field] is None:
            return jsonify({"detail": f"{field.replace('_', ' ').title()} is required"}), 400

    now = datetime.utcnow()
    counter = mongo.db.counters.find_one_and_update(
        {"_id": "transaction_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    transaction_id = f"TXN-{counter['seq']}"

    contribution_data = {
        "transaction_id": transaction_id,
        "member_id": int(data['member_id']),
        "amount": float(data['amount']),
        "payment_method": data['payment_method'],
        "purpose": data['purpose'],
        "date": now,
        "month": now.month,
        "year": now.year,
        "recorded_by": data.get("recorded_by", "system")
    }

    contributions_collection.insert_one(contribution_data)
    return jsonify({
        "message": "Contribution recorded successfully",
        "transaction_id": transaction_id
    }), 201


@app.route('/api/contributions', methods=['GET'])
def get_contributions():
    if 'username' not in session:
        return jsonify({"detail": "Unauthorized"}), 401

    member_id = request.args.get('member_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = {}
    if member_id:
        query["member_id"] = int(member_id)
    if start_date and end_date:
        query["date"] = {
            "$gte": datetime.strptime(start_date, "%Y-%m-%d"),
            "$lte": datetime.strptime(end_date, "%Y-%m-%d")
        }

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    skip = (page - 1) * per_page

    total = contributions_collection.count_documents(query)
    contributions = list(contributions_collection.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(per_page))

    return jsonify({
        "data": contributions,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        }
    })


@app.route('/api/stats')
def get_stats():
    now = datetime.utcnow()
    month = now.month
    year = now.year

    total_members = members_collection.count_documents({})
    this_month_total = sum(doc['total'] for doc in contributions_collection.aggregate([
        {"$match": {"month": month, "year": year}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]) or [{"total": 0}])
    this_year_total = sum(doc['total'] for doc in contributions_collection.aggregate([
        {"$match": {"year": year}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]) or [{"total": 0}])
    total_collected = sum(doc['total'] for doc in contributions_collection.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]) or [{"total": 0}])

    return jsonify({
        "total_members": total_members,
        "this_month": this_month_total,
        "this_year": this_year_total,
        "total_collected": total_collected
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
