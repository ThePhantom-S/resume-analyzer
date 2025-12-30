import os
import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from dotenv import load_dotenv

load_dotenv()

# Path to your NEW serviceAccountKey.json
service_account_path = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")

if not firebase_admin._apps:
    cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(cred)

security = HTTPBearer()

async def verify_firebase_token(res: HTTPAuthorizationCredentials = Security(security)):
    """Verifies the token from the new Firebase project."""
    token = res.credentials
    try:
        # This confirms the token was issued by your new project
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print(f"Neural Handshake Failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid Neural Link Token")