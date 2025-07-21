# Project Path: config.py
# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KEYWORDS_FILE = os.path.join(BASE_DIR, "resources/custom_keywords_sorted.txt")
STOPWORDS_FILE = os.path.join(BASE_DIR, "resources/stopwords.txt")

IMAGE_FORMAT = "PNG"
CELL_SIZE = 100
SUPPORTED_VIDEO_EXT = ['.mp4', '.avi', '.mov', '.mkv']
