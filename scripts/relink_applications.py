"""Re-link unlinked applications to jobs by company_key."""
import sys
from pathlib import Path

# Bootstrap
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.persistence.database import get_session, init_db
from src.persistence.models import normalize_company_key
from sqlalchemy import text

init_db()

with get_session() as session:
    # 1. Link World Wide Technology to its matching job
    wwt_jobs = session.execute(text(
        "SELECT id, title, description FROM jobs "
        "WHERE LOWER(company) LIKE :pat "
        "ORDER BY discovered_at DESC LIMIT 1"
    ), {'pat': '%world wide technology%'}).fetchall()

    if wwt_jobs:
        job_id, job_title, job_desc = wwt_jobs[0]
        session.execute(text(
            "UPDATE applications SET job_id = :job_id, job_description = :desc "
            "WHERE LOWER(company) LIKE :pat"
        ), {'job_id': job_id, 'desc': job_desc, 'pat': '%world wide technology%'})
        print(f'Linked WWT -> {job_title}')

    # 2. Link Twilio to best matching PM job
    twilio_jobs = session.execute(text(
        "SELECT id, title, description FROM jobs "
        "WHERE LOWER(company) = :co AND LOWER(title) LIKE :pat "
        "ORDER BY discovered_at DESC LIMIT 1"
    ), {'co': 'twilio', 'pat': '%product m%'}).fetchall()

    if twilio_jobs:
        job_id, job_title, job_desc = twilio_jobs[0]
        session.execute(text(
            "UPDATE applications SET job_id = :job_id, job_description = :desc "
            "WHERE LOWER(company) = :co"
        ), {'job_id': job_id, 'desc': job_desc, 'co': 'twilio'})
        print(f'Linked Twilio -> {job_title}')

    # 3. Bulk re-link ALL unlinked applications by company_key
    unlinked = session.execute(text(
        "SELECT a.id, a.company, a.company_key "
        "FROM applications a "
        "WHERE a.job_id IS NULL AND a.company_key IS NOT NULL AND LENGTH(a.company_key) > 0"
    )).fetchall()

    print(f'Unlinked applications to try: {len(unlinked)}')
    linked_count = 0
    for app_id, company, key in unlinked:
        job = session.execute(text(
            "SELECT id, title, description FROM jobs "
            "WHERE company_key = :key "
            "ORDER BY discovered_at DESC LIMIT 1"
        ), {'key': key}).fetchone()

        if job:
            job_id, job_title, job_desc = job
            if job_desc:
                session.execute(text(
                    "UPDATE applications SET job_id = :job_id, job_description = :desc WHERE id = :app_id"
                ), {'job_id': job_id, 'desc': job_desc, 'app_id': app_id})
            else:
                session.execute(text(
                    "UPDATE applications SET job_id = :job_id WHERE id = :app_id"
                ), {'job_id': job_id, 'app_id': app_id})
            linked_count += 1
            print(f'  Linked: {company} -> {job_title}')

    session.commit()
    print(f'Bulk re-linking complete: {linked_count} newly linked')

    # Final counts
    stats = session.execute(text(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN job_id IS NOT NULL THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN job_description IS NOT NULL AND LENGTH(job_description) > 0 THEN 1 ELSE 0 END) "
        "FROM applications"
    )).fetchone()
    print(f'Final: {stats[0]} total, {stats[1]} with job_id, {stats[2]} with description')

    # Rejections
    print()
    print('Rejections:')
    rej = session.execute(text(
        "SELECT company, position, "
        "CASE WHEN job_id IS NOT NULL THEN 'YES' ELSE 'NO' END, "
        "CASE WHEN job_description IS NOT NULL AND LENGTH(job_description) > 0 THEN 'YES' ELSE 'NO' END, "
        "COALESCE(LENGTH(job_description), 0) "
        "FROM applications WHERE status = 'rejected' ORDER BY company"
    )).fetchall()
    for r in rej:
        print(f'  {r[0]:35s} | {str(r[1])[:30]:30s} | job={r[2]} | desc={r[3]} | len={r[4]}')
