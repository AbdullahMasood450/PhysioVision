from pymongo import MongoClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# Initialize FastAPI app
app = FastAPI()

uri = "mongodb+srv://abdullahmasood450:harry_potter123@cluster0.ys9yt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# Middleware for CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace '*' with your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = None
db = None
collection_users = None


@app.on_event("startup")
def startup_db_client():
    global client, db, collection_users
    client = MongoClient(uri)
    db = client["PhysioVision"]
    collection_users =  db["Users"]   
    print("Connected to the MongoDB database!")


# Pydantic model
class UserSignUp(BaseModel):
    name: str
    username: str
    email: str
    password: str

# User sign-up route
@app.post("/api/signup")
async def sign_up(user: UserSignUp):
    try:
        user_data = user.dict()  # Convert Pydantic model to dictionary
        result = collection_users.insert_one(user_data)  # Insert the document
        return {"message": "User registered successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

