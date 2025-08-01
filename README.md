# AI Reviewer Assistant (NLE, MTLE)

Run this app:

```bash
uvicorn app.main:app --reload
```

To (re)build index:
```bash
python app/internal/builder.py
```

POST a question to:
```http
POST /ask
{ "question": "Explain ELISA" }
```

Update user:
```bash
PUT /admin/users/{username}
Authorization: Bearer <admin_token>
Content-Type: application/json

---