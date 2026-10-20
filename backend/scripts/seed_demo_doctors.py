import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.database import get_supabase_client

def seed_demo_doctors():
    client = get_supabase_client()
    if not client:
        print("Error: Supabase client could not be initialized.")
        return

    staff_defs = [
        {
            "email": "dr.sharma@cityhospital.org",
            "password": "Password123!",
            "hospital_id": "33333333-3333-3333-3333-333333333333",
            "full_name": "Dr. Ananya Sharma",
            "employee_id": "EMP-CGH-101",
            "role": "clinician",
            "department": "Internal Medicine",
            "reg_no": "MCI-2018-98421"
        },
        {
            "email": "dr.patel@metroclinic.org",
            "password": "Password123!",
            "hospital_id": "44444444-4444-4444-4444-444444444444",
            "full_name": "Dr. Rajesh Patel",
            "employee_id": "EMP-MSC-502",
            "role": "clinician",
            "department": "Cardiology",
            "reg_no": "MCI-2015-77319"
        }
    ]

    all_users = client.auth.admin.list_users()

    for s in staff_defs:
        user_id = None
        matched = [u for u in all_users if getattr(u, 'email', None) == s['email']]
        if matched:
            user_id = matched[0].id
            print(f"Found existing auth user for {s['email']}: {user_id}")
        else:
            u = client.auth.admin.create_user({
                "email": s["email"],
                "password": s["password"],
                "email_confirm": True,
                "user_metadata": {"full_name": s["full_name"], "role": "hospital_staff"}
            })
            user_id = u.user.id
            print(f"Created auth user for {s['email']}: {user_id}")
        
        # Upsert into public.users
        client.table("users").upsert({
            "id": user_id,
            "email": s["email"],
            "role": "hospital_staff",
            "is_active": True
        }).execute()
        print(f"Upserted public.users for {user_id}")

        # Upsert into public.hospital_staff
        existing_staff = client.table("hospital_staff").select("id").eq("user_id", user_id).execute().data
        if existing_staff:
            client.table("hospital_staff").update({
                "hospital_id": s["hospital_id"],
                "employee_id": s["employee_id"],
                "role": s["role"],
                "department": s["department"],
                "clinical_registration_number": s["reg_no"],
                "is_active": True
            }).eq("user_id", user_id).execute()
            print(f"Updated hospital_staff for {user_id}")
        else:
            client.table("hospital_staff").insert({
                "user_id": user_id,
                "hospital_id": s["hospital_id"],
                "employee_id": s["employee_id"],
                "role": s["role"],
                "department": s["department"],
                "clinical_registration_number": s["reg_no"],
                "is_active": True
            }).execute()
            print(f"Inserted hospital_staff for {user_id}")

if __name__ == "__main__":
    seed_demo_doctors()
