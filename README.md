# LeadLock - Cheshire Stables Sales Control

Premium lead management system for Cheshire Stables. A calm, authoritative web application that controls the sales workflow with strict quote locking and role-based permissions.

## Features

- **Role-Based Access Control**: Director, Sales Manager, and Closer roles with different workflow permissions
- **Strict Quote Lock**: Prevents quotes from being sent until all prerequisites are met
- **Workflow State Machine**: Enforced server-side transitions (NEW → CONTACT_ATTEMPTED → ENGAGED → QUALIFIED → QUOTED → WON/LOST)
- **Activity Logging**: Track SMS, calls, emails, and WhatsApp communications
- **SLA Monitoring**: Visual badges for overdue leads
- **Premium UI**: Dark green theme matching Cheshire Stables branding

## Tech Stack

- **Backend**: FastAPI + SQLModel + PostgreSQL
- **Frontend**: Next.js 14+ (App Router) + TypeScript + TailwindCSS + shadcn/ui
- **Auth**: JWT (email/password)
- **Database**: PostgreSQL (deployed on Railway)

## Project Structure

```
LeadLock/
├── api/                 # FastAPI backend
│   ├── app/
│   │   ├── models.py    # SQLModel database models
│   │   ├── auth.py      # JWT authentication
│   │   ├── workflow.py  # State machine & quote lock logic
│   │   ├── routers/     # API endpoints
│   │   └── main.py      # FastAPI app
│   ├── seed.py          # Database seeding script
│   └── requirements.txt
├── web/                 # Next.js frontend
│   ├── app/             # App Router pages
│   ├── components/      # React components
│   └── lib/             # Utilities & API client
└── README.md
```

## Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL database (local or Railway)

### Backend Setup

1. Navigate to the API directory:
```bash
cd api
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. For local development, create a `.env` file in the `api/` directory:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/leadlock
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

**Note:** For Railway deployment, set these as environment variables in the Railway dashboard. Railway automatically provides `DATABASE_URL` when you add a PostgreSQL service.

5. Run the seed script to create initial users:
```bash
python seed.py
```

This creates three test users:
- `director@cheshirestables.com` / `director123` (DIRECTOR role)
- `manager@cheshirestables.com` / `manager123` (SALES_MANAGER role)
- `closer@cheshirestables.com` / `closer123` (CLOSER role)

6. Start the FastAPI server:
```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to the web directory:
```bash
cd web
```

2. Install dependencies:
```bash
npm install
```

3. Create a `.env.local` file in the `web/` directory:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

4. Start the development server:
```bash
npm run dev
```

The app will be available at `http://localhost:3000`

## Environment Variables

### Backend (`api/.env`)

- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: JWT secret key (use a strong random string in production)
- `ALGORITHM`: JWT algorithm (default: HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Token expiration time (default: 1440 = 24 hours)
- `WEBHOOK_API_KEY`: Secret API key for webhook authentication (required for Make.com integration)
- `WEBHOOK_DEFAULT_USER_ID`: (Optional) User ID to assign webhook-created leads to. If not set, leads will be unassigned.
- `CLOUDINARY_CLOUD_NAME`: (Optional) Cloudinary cloud name for image uploads. If not set, images will be stored locally.
- `CLOUDINARY_API_KEY`: (Optional) Cloudinary API key
- `CLOUDINARY_API_SECRET`: (Optional) Cloudinary API secret

**Note:** See `CLOUDINARY_SETUP.md` for detailed Cloudinary setup instructions.

### Frontend (`web/.env.local`)

- `NEXT_PUBLIC_API_URL`: Backend API URL (default: http://localhost:8000)

## Workflow & Roles

### Workflow States

1. **NEW**: Initial lead state
2. **CONTACT_ATTEMPTED**: First contact made
3. **ENGAGED**: Lead has responded (auto-transitions on engagement proof)
4. **QUALIFIED**: Lead meets qualification criteria
5. **QUOTED**: Quote sent (locked until prerequisites met)
6. **WON**: Deal closed successfully
7. **LOST**: Lead lost

### Role Permissions

**DIRECTOR**
- Full access to all transitions
- Can override any workflow rule (reason required)
- Can move leads to any status

**SALES_MANAGER**
- Can move: NEW → CONTACT_ATTEMPTED → ENGAGED → QUALIFIED
- Cannot quote or close deals

**CLOSER**
- Can move: QUALIFIED → QUOTED → WON/LOST
- Focused on closing qualified leads

### Quote Lock Requirements

A lead can ONLY move to QUOTED if:

1. Status is QUALIFIED
2. Engagement proof exists (one of):
   - SMS_RECEIVED
   - EMAIL_RECEIVED
   - WHATSAPP_RECEIVED
   - LIVE_CALL
3. Required fields present:
   - `postcode`
   - `timeframe` != UNKNOWN
   - `scope_notes` OR `product_interest`

If blocked, the API returns structured errors:
```json
{
  "error": "QUOTE_PREREQS_MISSING",
  "missing": ["postcode", "timeframe"]
}
```

or

```json
{
  "error": "NO_ENGAGEMENT_PROOF",
  "message": "No engagement proof found..."
}
```

## Make.com Webhook Integration

To create leads from Make.com webhooks, use the dedicated webhook endpoint `/api/webhooks/leads`:

**Endpoint:** `POST /api/webhooks/leads`

**Headers:**
```
X-API-Key: <your-webhook-api-key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "+44 1234 567890",
  "postcode": "CW1 2AB",
  "description": "Interested in custom stable design for 4 horses"
}
```

**Setup:**
1. Set `WEBHOOK_API_KEY` environment variable in your backend (generate a strong random string)
2. Optionally set `WEBHOOK_DEFAULT_USER_ID` to automatically assign webhook-created leads to a specific user
3. Configure Make.com to send POST requests to `https://your-api-url/api/webhooks/leads` with the `X-API-Key` header

**Response:**
The endpoint returns the created lead with status `NEW`. If `WEBHOOK_DEFAULT_USER_ID` is set, the lead will be assigned to that user; otherwise, it will be unassigned.

**Note:** All fields except `name` are optional. The `description` field can be used to store additional information about the lead.

## Replacing the Logo

The logo component is located at `web/components/Logo.tsx`. To replace it:

1. Add your logo file to `web/public/logo.svg` (or your preferred format)
2. Update `Logo.tsx`:

```tsx
import Image from 'next/image';

export default function Logo() {
  return (
    <div className="flex items-center gap-3">
      <Image src="/logo.svg" alt="Cheshire Stables" width={120} height={40} />
      <div className="flex flex-col">
        <span className="text-xl font-semibold text-white tracking-tight">
          LeadLock
        </span>
        <span className="text-xs text-muted-foreground">
          Cheshire Stables Sales Control
        </span>
      </div>
    </div>
  );
}
```

## Brand Colors

The app uses Cheshire Stables brand colors:

- **Dark green background**: `#0F2E1E`
- **Primary surface/cards**: `#163F2A`
- **Brand green (primary accents)**: `#1F6B3A`
- **Success / unlocked green**: `#3FA86B`
- **Silver / stone**: `#C8C9C7`
- **Muted grey text**: `#9DA7A0`
- **White text**: `#FFFFFF`

Colors are defined in `web/app/globals.css`.

## Deployment

### Backend (Railway)

1. Connect your GitHub repository to Railway
2. **Important**: Do NOT set a Root Directory in Railway settings - keep it as the repository root
   - Railway will use the root-level `Procfile`, `railway.json`, and `nixpacks.toml` which reference the `api/` directory
3. Add a PostgreSQL service (Railway will automatically set `DATABASE_URL`)
4. Set these environment variables in Railway dashboard:
   - `SECRET_KEY` - Generate a strong random string (e.g., `openssl rand -hex 32`)
   - `ALGORITHM` - `HS256` (default)
   - `ACCESS_TOKEN_EXPIRE_MINUTES` - `1440` (default, 24 hours)
5. Railway will auto-detect Python via Nixpacks and deploy using the root-level `Procfile`
6. After deployment, run the seed script to create initial users:
   ```bash
   railway run cd api && python seed.py
   ```
   Or use Railway's CLI from your local machine:
   ```bash
   railway run --service <your-service-name> sh -c "cd api && python seed.py"
   ```
7. The API will be available at your Railway-provided URL

### Frontend (Vercel/Netlify)

1. Connect your GitHub repository
2. Set `NEXT_PUBLIC_API_URL` to your Railway API URL
3. Deploy

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Get current user

### Leads
- `GET /api/leads` - List leads (with filters)
- `GET /api/leads/{id}` - Get lead details
- `POST /api/leads` - Create lead (requires JWT authentication)
- `PATCH /api/leads/{id}` - Update lead
- `POST /api/leads/{id}/transition` - Change lead status
- `GET /api/leads/{id}/allowed-transitions` - Get allowed transitions
- `POST /api/leads/{id}/activities` - Log activity
- `GET /api/leads/{id}/activities` - Get activity timeline
- `GET /api/leads/{id}/status-history` - Get status change history

### Webhooks
- `POST /api/webhooks/leads` - Create lead via webhook (API key authentication)

### Dashboard
- `GET /api/dashboard/stats` - Get dashboard statistics
- `GET /api/dashboard/stuck-leads` - Get stuck leads

## Development

### Running Tests

Backend tests (when added):
```bash
cd api
pytest
```

Frontend tests (when added):
```bash
cd web
npm test
```

### Database Migrations

SQLModel creates tables automatically on first run. For production, consider using Alembic for migrations.

## License

Proprietary - Cheshire Stables
#   l e a d l o c k 
 
 