# API examples

## Register customer

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"customer@example.com","password":"password123","display_name":"Ada","role":"customer"}'
```

## Register professional

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"pro@example.com","password":"password123","display_name":"David","role":"professional"}'
```

Use the returned access token as:

```text
Authorization: Bearer ACCESS_TOKEN
```

## Create professional profile

```bash
curl -X POST http://localhost:8000/professionals/me \
  -H 'Authorization: Bearer PRO_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"headline":"Premium Product Designer","bio":"I design high-converting digital products.","years_experience":7}'
```

## Search

```bash
curl 'http://localhost:8000/professionals?q=designer'
```
