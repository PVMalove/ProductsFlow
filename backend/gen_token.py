import uuid, sys
sys.path.insert(0, 'services/identity-service/src')
from core.settings import settings
settings.identity_jwt_private_key_path = 'secrets/identity_jwt_private_key.pem'
from core.security.tokens import create_access_token
print(create_access_token('00000000-0000-0000-0000-000000000001'))
