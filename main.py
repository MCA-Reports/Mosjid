# main.py
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, timedelta
import jWT
import bcrypt
import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from bson import ObjectId

# MongoDB setup
MONGODB_URL = "mongodb+srv://bdkz:bdkz2025@cluster0.yc3hbgc.mongodb.net/mosque_finance?retryWrites=true&w=majority"
client = AsyncIOMotorClient(MONGODB_URL)
db = client["mosque_finance"]

# Collections
users_collection = db["users"]
members_collection = db["members"]
contributions_collection = db["contributions"]
income_collection = db["income"]
expenses_collection = db["expenses"]

# JWT Configuration
SECRET_KEY = "your-secret-key-here"  # Change this in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Pydantic Models
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    is_admin: bool = False

class UserLogin(BaseModel):
    username: str
    password: str

class MemberCreate(BaseModel):
    first_name: str
    last_name: str
    mobile_no: str
    city: str
    user_type: str
    fixed_amount: float = 0.0

class ContributionCreate(BaseModel):
    member_id: str
    month: str
    year: int
    amount: float

class IncomeCreate(BaseModel):
    description: str
    amount: float

class ExpenseCreate(BaseModel):
    description: str
    amount: float

# FastAPI app
app = FastAPI(title="Mosque Finance Management", version="1.0.0")

# Security
security = HTTPBearer()

# Templates and static files
templates = Jinja2Templates(directory="templates")
Path("templates").mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)

# Helper functions
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8', 'ignore')

def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

async def get_current_user(username: str = Depends(verify_token)):
    user = await users_collection.find_one({"username": username})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_admin_user(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Initialize admin user on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    admin_user = await users_collection.find_one({"username": "admin"})
    if not admin_user:
        hashed_password = hash_password("admin123")
        admin_user = {
            "username": "admin",
            "email": "admin@mosque.com",
            "hashed_password": hashed_password,
            "is_admin": True,
            "created_at": datetime.utcnow()
        }
        await users_collection.insert_one(admin_user)
        print("Admin user created: username=admin, password=admin123")
    yield

app.router.lifespan_context = lifespan

# Routes
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

# Authentication
@app.post("/api/register")
async def register_user(user: UserCreate):
    if await users_collection.find_one({"username": user.username}):
        raise HTTPException(status_code=400, detail="Username already registered")
    if await users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = hash_password(user.password)
    db_user = {
        "username": user.username,
        "email": user.email,
        "hashed_password": hashed_password,
        "is_admin": user.is_admin,
        "created_at": datetime.utcnow()
    }
    await users_collection.insert_one(db_user)
    return {"message": "User registered successfully"}

@app.post("/api/login")
async def login(user: UserLogin):
    db_user = await users_collection.find_one({"username": user.username})
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": db_user["username"]})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_admin": db_user.get("is_admin", False)
    }

# Members
@app.post("/api/members")
async def create_member(member: MemberCreate, current_user: dict = Depends(get_current_user)):
    if await members_collection.find_one({"mobile_no": member.mobile_no}):
        raise HTTPException(status_code=400, detail="Mobile number already registered")
    
    db_member = member.dict()
    db_member["created_at"] = datetime.utcnow()
    result = await members_collection.insert_one(db_member)
    return {"message": "Member registered successfully!", "member_id": str(result.inserted_id)}

@app.get("/api/members")
async def get_members(current_user: dict = Depends(get_current_user)):
    members = []
    async for member in members_collection.find():
        members.append(member)
    return members

@app.get("/api/members/{member_id}")
async def get_member(member_id: str, current_user: dict = Depends(get_current_user)):
    member = await members_collection.find_one({"_id": ObjectId(member_id)})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    contributions = []
    async for contribution in contributions_collection.find({"member_id": member_id}):
        contributions.append(contribution)
    
    return {"member": member, "contributions": contributions}

# Contributions
@app.post("/api/contributions")
async def create_contribution(contribution: ContributionCreate, current_user: dict = Depends(get_current_user)):
    member = await members_collection.find_one({"_id": ObjectId(contribution.member_id)})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    db_contribution = contribution.dict()
    db_contribution["member_id"] = str(member["_id"])  # ensure stored as string
    db_contribution["created_at"] = datetime.utcnow()
    await contributions_collection.insert_one(db_contribution)
    return {"message": "Contribution added successfully!"}

@app.get("/api/contributions")
async def get_contributions(current_user: dict = Depends(get_current_user)):
    contributions = []
    async for contribution in contributions_collection.find():
        contributions.append(contribution)
    return contributions

# Income & expenses
@app.post("/api/income")
async def create_income(income: IncomeCreate, current_user: dict = Depends(get_admin_user)):
    db_income = income.dict()
    db_income["date"] = datetime.utcnow()
    db_income["added_by"] = current_user["_id"]
    await income_collection.insert_one(db_income)
    return {"message": "Income added successfully!"}

@app.post("/api/expenses")
async def create_expense(expense: ExpenseCreate, current_user: dict = Depends(get_admin_user)):
    db_expense = expense.dict()
    db_expense["date"] = datetime.utcnow()
    db_expense["added_by"] = current_user["_id"]
    await expenses_collection.insert_one(db_expense)
    return {"message": "Expense added successfully!"}

@app.get("/api/income")
async def get_income(current_user: dict = Depends(get_current_user)):
    income = []
    async for item in income_collection.find():
        income.append(item)
    return income

@app.get("/api/expenses")
async def get_expenses(current_user: dict = Depends(get_current_user)):
    expenses = []
    async for expense in expenses_collection.find():
        expenses.append(expense)
    return expenses

# Dashboard
@app.get("/api/dashboard")
async def get_dashboard_data(current_user: dict = Depends(get_current_user)):
    total_members = await members_collection.count_documents({})
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    
    total_contributions = await contributions_collection.aggregate(pipeline).to_list(1)
    total_income = await income_collection.aggregate(pipeline).to_list(1)
    total_expenses = await expenses_collection.aggregate(pipeline).to_list(1)
    
    recent_contributions = []
    async for contribution in contributions_collection.find().sort("created_at", -1).limit(10):
        recent_contributions.append(contribution)
    
    return {
        "total_members": total_members,
        "total_contributions": total_contributions[0]["total"] if total_contributions else 0,
        "total_income": total_income[0]["total"] if total_income else 0,
        "total_expenses": total_expenses[0]["total"] if total_expenses else 0,
        "net_balance": (total_contributions[0]["total"] if total_contributions else 0)
                        + (total_income[0]["total"] if total_income else 0)
                        - (total_expenses[0]["total"] if total_expenses else 0),
        "recent_contributions": recent_contributions
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
