import os
from pathlib import Path
import tempfile


TEST_DIR = Path(tempfile.mkdtemp(prefix="hr-agent-tests-"))
os.environ["HR_DATABASE_URL"] = f"sqlite:///{(TEST_DIR / 'test.db').as_posix()}"
os.environ["HR_ENVIRONMENT"] = "test"
os.environ["HR_AUTH_REQUIRED"] = "true"
os.environ["HR_JWT_SECRET"] = "test-only-jwt-secret-with-more-than-32-characters"
os.environ["HR_DATA_ENCRYPTION_KEY"] = "zq7_HdO6ir9-6tIS_CuXCiyzF1_wEf0iP8scq4kLnYg="
