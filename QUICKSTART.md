# Quick Start Guide

## 1. Backend Setup (5 minutes)

```bash
cd api

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
DATABASE_URL=postgresql://user:password@localhost:5432/leadlock
SECRET_KEY=change-this-to-a-random-string-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
EOF

# Seed database
python seed.py

# Start server
uvicorn app.main:app --reload --port 8000
```

## 2. Frontend Setup (3 minutes)

```bash
cd web

# Install dependencies
npm install

# Create .env.local file
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start dev server
npm run dev
```

## 3. Login

Open http://localhost:3000 and login with:
- **Director**: `director@cheshirestables.com` / `director123`
- **Manager**: `manager@cheshirestables.com` / `manager123`
- **Closer**: `closer@cheshirestables.com` / `closer123`

## 4. Test the Quote Lock

1. Create a new lead (or use existing)
2. Move it to QUALIFIED status
3. Notice the "🔒 Quote Locked" card appears
4. Fill in postcode, timeframe, and scope notes
5. Log an activity: "SMS Received" or "Live Call"
6. Watch the lock unlock! 🔓

## Next Steps

- **Deploy to Railway**: 
  - Add PostgreSQL service (Railway sets `DATABASE_URL` automatically)
  - Set `SECRET_KEY` environment variable in Railway dashboard
  - Run `python seed.py` via Railway CLI or one-off command
- Update CORS origins in `api/app/main.py` for production (add your Railway API URL)
- Replace logo in `web/components/Logo.tsx`
- Set up Make.com webhook to create leads automatically (use your Railway API URL)
