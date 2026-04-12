from app.core.security import hash_password

senha = "123456"
print(len(senha))  # debug

hash_senha = hash_password(senha)

print(hash_senha)