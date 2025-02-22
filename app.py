from flask import Flask, render_template, request, jsonify
import pandas as pd
import os

app = Flask(__name__)
FILE_PATH = "mosjid_data.xlsx"

# Ensure the Excel file exists
def load_or_create_excel():
    if not os.path.exists(FILE_PATH):
        with pd.ExcelWriter(FILE_PATH, engine="openpyxl") as writer:
            pd.DataFrame(columns=["ID", "First Name", "Last Name", "Mobile No", "City", "User Type", "Fixed Amount"]).to_excel(writer, sheet_name="Registrations", index=False)
            pd.DataFrame(columns=["ID", "Month", "Year", "Amount"]).to_excel(writer, sheet_name="Contributions", index=False)

load_or_create_excel()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    df = pd.read_excel(FILE_PATH, sheet_name="Registrations")

    # Assign the next available ID (1 to 1000)
    next_id = str(len(df) + 1) if len(df) < 1000 else "Limit Reached"

    if next_id == "Limit Reached":
        return jsonify({"success": False, "message": "Registration limit reached (1-1000 IDs allowed)."})

    new_entry = pd.DataFrame([{
        "ID": next_id,
        "First Name": request.form["first_name"],
        "Last Name": request.form["last_name"],
        "Mobile No": request.form["mobile_no"],
        "City": request.form["city"],
        "User Type": request.form["user_type"],
        "Fixed Amount": request.form["fixed_amount"],
    }])

    df = pd.concat([df, new_entry], ignore_index=True)

    with pd.ExcelWriter(FILE_PATH, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df.to_excel(writer, sheet_name="Registrations", index=False)

    return jsonify({"success": True, "message": f"Member Registered! ID: {next_id}"})

@app.route("/search", methods=["POST"])
def search():
    member_id = request.form["member_id"]
    reg_df = pd.read_excel(FILE_PATH, sheet_name="Registrations")
    contrib_df = pd.read_excel(FILE_PATH, sheet_name="Contributions")

    # Fetch member details
    member_data = reg_df[reg_df["ID"].astype(str) == member_id]
    if member_data.empty:
        return jsonify({"success": False, "message": "Member not found."})

    member_info = member_data.to_dict(orient="records")[0]

    # Fetch contribution history
    contrib_history = contrib_df[contrib_df["ID"].astype(str) == member_id]
    contributions = contrib_history.to_dict(orient="records")

    return jsonify({"success": True, "member": member_info, "contributions": contributions})

@app.route("/contribute", methods=["POST"])
def contribute():
    reg_df = pd.read_excel(FILE_PATH, sheet_name="Registrations")
    contrib_df = pd.read_excel(FILE_PATH, sheet_name="Contributions")

    member_id = request.form["member_id"]
    month = request.form["month"]
    year = request.form["year"]
    amount = request.form["amount"]

    # Check if member exists before adding contribution
    if not reg_df[reg_df["ID"].astype(str) == member_id].empty:
        new_entry = pd.DataFrame([{
            "ID": member_id,
            "Month": month,
            "Year": year,
            "Amount": amount,
        }])

        contrib_df = pd.concat([contrib_df, new_entry], ignore_index=True)

        with pd.ExcelWriter(FILE_PATH, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            contrib_df.to_excel(writer, sheet_name="Contributions", index=False)

        return jsonify({"success": True, "message": "Contribution Added Successfully!"})
    else:
        return jsonify({"success": False, "message": "Invalid Member ID. Please register first."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

