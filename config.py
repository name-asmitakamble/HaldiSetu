import os
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "haldisetu.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB upload limit
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.70"))
    MODEL_VERSION = os.getenv("MODEL_VERSION", "mobilenetv2-v1")
    MODEL_PATH = os.path.join(BASE_DIR, "ml", "haldisetu_model.keras")
    LABELS_PATH = os.path.join(BASE_DIR, "ml", "class_labels.json")
