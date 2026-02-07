"""Backfill job descriptions for rejected applications from web research."""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.persistence.database import get_session, init_db
from sqlalchemy import text

MAX_DESC_LENGTH = 2000

# Research results: company -> (position, description)
UPDATES = {
    "aristocrat": (
        "Product Manager I, Technology Platform",
        "Join Aristocrat's Technology Product Management team to product manage current and future "
        "land-based game technologies (gaming market platform/OS, game engine/development kits, and "
        "game production tools). Strategize plans 3-5 years in advance, defining vision and executing "
        "broad-based strategy with product roadmap. Work closely with game development studios, hardware "
        "and software engineering teams, customers, regulatory agencies, and sales/marketing organizations. "
        "Interact with multiple stakeholder groups and senior management to lead product planning exercises. "
        "Ensure market requirements and customer needs are built into future product releases. Collaborate "
        "with engineering teams to assess product requirements and organize product reviews and roadmap "
        "alignment meetings. Interpret customer and market insights. Develop business cases with Finance. "
        "Required: 2+ years product management experience (slots experience preferred). Thorough understanding "
        "of product development lifecycle. Ability to comprehend technical challenges, understand limitations "
        "and impact to customers. Experience working with hardware engineers, project managers, program managers. "
        "Self-starter with demonstrated initiative. Preferred: Advanced degree, casino industry or gaming "
        "product development experience, Product Management certification. Location: Las Vegas, NV. "
        "Salary: $67,470-$125,301. Must be authorized to work in US. Subject to gaming regulatory "
        "approvals and background checks. Aristocrat is a global entertainment and content creation company, "
        "world leader in gaming content and technology, top-tier publisher of free-to-play mobile games. "
        "7,300+ employees across 20+ locations globally."
    ),
    "federato": (
        "Senior Product Manager",
        "Own the roadmap of Federato's underwriting platform and actively seek opportunities to expand "
        "capabilities. Define product vision aligned with company objectives and financial goals. Develop "
        "long-term roadmaps based on market analysis and user needs. Communicate value propositions to "
        "stakeholders; build relationships across sales, marketing, and customer success. Analyze insurance "
        "market dynamics, competitive landscape, and identify M&A opportunities. Conduct user research "
        "activities and synthesize findings into actionable insights. Lead product discovery efforts, validate "
        "user problems, create requirements for engineering. Define and track metrics; analyze trends informing "
        "product decisions. Work with engineering, design, and business teams on strategy and execution. "
        "Required: BA/BS in business, computer science, engineering, or related field. Proven track record "
        "delivering successful B2B SaaS products. Strong business acumen. Excellent communication, "
        "collaboration, and interpersonal skills. Technical understanding of software development methodologies. "
        "Strong analytical and problem-solving abilities. Preferred: MBA, insurance or financial industry "
        "experience, AI-powered solutions background, ability to travel to East Coast ~30% of time. "
        "Salary: $170,000-$200,000 + stock options, bonus, benefits. Location: Remote. "
        "Federato is an insurance technology startup (Series D, $182.4M raised) providing an AI-native "
        "insurance platform for the full policy lifecycle, serving underwriters, portfolio managers, and "
        "actuaries in the P&C and Specialty insurance industry."
    ),
    "fontainebleau": (
        "Product Senior Manager, Digital Technology",
        "Serve as the primary Digital Tech liaison for marketing business partners at Fontainebleau Las Vegas, "
        "aligning tech services with strategic objectives. Develop and implement comprehensive digital strategy "
        "and vision. Lead development teams, manage projects, foster culture of collaboration and high "
        "performance. Drive integration and optimization of Customer Data Platform (CDP) to unify customer "
        "profiles and enable targeted marketing. Support digital marketing campaigns across channels. Lead "
        "product management efforts for web and mobile platforms (responsive web, mobile web, native apps). "
        "Translate business needs into detailed product requirements. Collaborate with design and development "
        "teams to deliver high-quality digital experiences. Define and manage product roadmaps. Write user "
        "stories and lead cross-functional teams through the product lifecycle. Identify opportunities for "
        "digital transformation. Oversee projects from inception to completion. Partner with IT service "
        "management process owners on incident, problem, and change management. "
        "Required: Bachelor's Degree in STEM or Business (Master's preferred). 8+ years as Product Manager "
        "delivering software products. Deep expertise in MarTech including CDP, digital campaign orchestration. "
        "Product management experience for digital platforms. Proficiency with Figma, Miro, Mural, Confluence, "
        "Jira. Strong SDLC understanding. Understanding of ITIL frameworks. Exceptional communication skills. "
        "Salary: $93,000-$166,000. Location: Las Vegas, NV. Must be 21+."
    ),
    "gartner": (
        "Product Manager (AI Products/AI Platform)",
        # No full description available — Gartner's careers site returned 403.
        # Using what we know from the email subject and company context.
        "Product Manager role at Gartner focused on AI Products and AI Platform. "
        "Job ID: 106867. Gartner uses Workday ATS. The posting was listed at "
        "jobs.gartner.com/jobs/job/106867-product-manager-ai-products-ai-platform/. "
        "Gartner is a global research and advisory company (NYSE: IT) providing insights, "
        "advice, and tools for leaders in IT, finance, HR, customer service, legal, and other "
        "business functions. The role likely involves managing AI-powered product features within "
        "Gartner's research and advisory platform. Note: Full job description could not be retrieved "
        "as the posting has been taken down and no cached version is available."
    ),
    "fetchrewards": (
        "Staff Product Manager – ML, Ranking & Personalization [Ads]",
        "Define and lead the ML-driven ranking, targeting, and personalization systems that power Fetch's "
        "ads business. Own the strategy and roadmap for how Fetch matches users to the most relevant ads "
        "and offers, optimizing for user experience, advertiser outcomes, and marketplace health. With more "
        "than $180B in annual purchase data, Fetch has the scale and signal richness to build one of the "
        "most effective retail media personalization engines in the industry. "
        "Responsibilities: Own vision, strategy, and roadmap for ML-driven ads ranking and personalization "
        "systems. Balance Fetch's goals, advertiser objectives, and consumer experience. Design system "
        "architecture — determine what logic lives in ad servers versus ML systems, defining boundaries, "
        "signals, and controls. Partner with cross-functional teams to translate advertiser goals into "
        "ranking objectives. Drive development of ranking models, signals, and real-time scoring "
        "infrastructure. Build experimentation frameworks that drive measurable improvements in relevance "
        "and ROI. Work closely with Engineering, ML, Analytics, Sales, and Go-To-Market teams. "
        "Requirements: 8+ years product management experience building ML-powered ranking, personalization, "
        "recommendation, ads, or search systems. Deep understanding of ML ranking, feature engineering, "
        "real-time scoring, user behavior modeling, and entity understanding. Preferred: experience in ads "
        "relevance, auction mechanics, targeting, or marketplace optimization. "
        "Benefits: Equity, 401(k) matching (dollar-for-dollar up to 4%), comprehensive medical/dental/vision, "
        "$10K annual education reimbursement, 20 weeks paid parental leave, flexible PTO, remote work option."
    ),
    "lead bank": (
        "Senior Product Manager",
        "Support the development of Lead's Banking as a Service (BaaS) platform, creating the pathway for "
        "clients to deliver innovative financial products relating to deposits, credit and lending, issuing "
        "and accepting credit/debit card transactions, and other embedded financial services. "
        "Break down ambiguous problems and ask the right questions when gathering data across cross-functional "
        "groups. Use structured first principles approach to unblock decisions and create a path forward. "
        "Develop and maintain a prioritized product roadmap with well-defined product requirements and "
        "business justifications. Maintain deep knowledge of technical and operational elements of your "
        "product. Develop clear product requirements to communicate with engineering teams and designers. "
        "Drive passion for changing the banking system to meet the needs of a modern digital economy. "
        "Required: 7+ years demonstrated experience in product management and/or engineering. Track record "
        "building world-class fintech products. Prior experience in enterprise software domain. Scalable "
        "SaaS platform design experience. Highly compliance-centric product experience. Experience building "
        "high-velocity, low-latency, high-availability services. Beautiful API design expertise. "
        "Highly analytical with first principles thinking. User-first mindset. Strong communication skills. "
        "Location: Remote. Lead Bank is an FDIC-insured fintech building banking infrastructure for embedded "
        "financial products, headquartered in Kansas City, MO with offices in SF, Sunnyvale, and NYC."
    ),
    "sortly": (
        "Senior Product Manager",
        "Drive development of new features, optimize current ones, and identify new opportunities aligned "
        "with company strategy at Sortly, a leading inventory management platform. "
        "Drive 0-to-1 product launches in fast-paced environments. Manage full product lifecycle: discovery, "
        "design, implementation, and go-to-market strategy. Apply Jobs-to-be-Done framework for B2B customers. "
        "Translate findings into actionable requirements. Align cross-functional teams across design, "
        "engineering, sales, and marketing. Develop messaging and positioning for features targeting ideal "
        "customer profiles. Partner with sales to understand requirements and demonstrate solutions. "
        "Define and prioritize features based on customer feedback, market research, and business goals. "
        "Conduct user interviews, research, and usability testing. Use analytics tools to inform decisions "
        "and measure feature impact. Create dashboards tracking KPIs. Tell compelling stories about product "
        "vision to stakeholders. Understand diverse customer bases across construction, HVAC, manufacturing, "
        "medical, and services industries. "
        "Required: 5+ years product management experience (B2B SaaS preferred). Inventory management or "
        "asset tracking experience a plus. Proven user research and synthesis skills. Proficiency with "
        "Amplitude, Looker, or Google Analytics. Strong engineering process understanding. Excellent "
        "communication for both technical and non-technical stakeholders. Multi-timezone collaboration. "
        "Salary: $140,000-$210,000. Location: New York, NY (Remote-Flexible). Reports to: Director of "
        "Product Management. Benefits: 401(k) matching, annual learning reimbursement, home office stipend, "
        "annual team retreats, comprehensive health/wellness coverage."
    ),
    "unframe": (
        "AI Product Manager",
        "Translate customer problems into structured solution plans using the Unframe.ai platform. Own "
        "end-to-end project delivery collaborating with engineers and AI specialists. Write detailed "
        "specifications and define prompt/context structures for solution logic. Prioritize requirements "
        "and manage tradeoffs across speed, stability, and scope. Work with the Platform team to identify "
        "reusable product patterns. Represent user needs from enterprise operators to domain experts. "
        "Serve as the voice of the user. Bridge product thinking with real-world use cases to enable fast, "
        "reliable delivery of custom solutions built on a shared core. "
        "Required: 4+ years in product management or technical delivery roles. Experience collaborating "
        "closely with engineering teams on technical products. Ability managing complex multi-part projects. "
        "Strong written communication, systems thinking, and attention to detail. Fluent English. "
        "Comfortable in fast-paced environments with changing requirements. "
        "Preferred: Background in enterprise software, AI tools, or internal platforms. Familiarity with "
        "prompt engineering, LLMs, or component-based systems. Experience with customers in finance, "
        "cybersecurity, or operations sectors. "
        "Location: New York, NY (also Tel Aviv and Berlin). Unframe is an AI company ($50M Series A from "
        "Bessemer, Craft, TLV Partners) building AI-powered enterprise solutions through their Blueprint-led "
        "approach platform, enabling organizations to deploy LLM applications rapidly without fine-tuning "
        "or data sharing requirements."
    ),
}


def main():
    init_db()

    with get_session() as session:
        for company_lower, (position, description) in UPDATES.items():
            # Truncate description to max length
            if len(description) > MAX_DESC_LENGTH:
                description = description[:MAX_DESC_LENGTH - 3] + "..."

            # Find the application
            app = session.execute(text(
                "SELECT id, company, position, job_description FROM applications "
                "WHERE LOWER(company) = :co"
            ), {'co': company_lower}).fetchone()

            if not app:
                print(f"  SKIP: No application found for '{company_lower}'")
                continue

            app_id = app[0]
            old_position = app[2]
            old_desc_len = len(app[3]) if app[3] else 0

            # Update position if currently "Unknown Position"
            if old_position == "Unknown Position":
                session.execute(text(
                    "UPDATE applications SET position = :pos WHERE id = :id"
                ), {'pos': position, 'id': app_id})
                print(f"  Updated position: {company_lower} -> {position}")
            elif old_position != position:
                print(f"  KEPT position: {company_lower} = '{old_position}' (researched: '{position}')")

            # Update description if empty or shorter than researched version
            if old_desc_len == 0 or old_desc_len < len(description):
                session.execute(text(
                    "UPDATE applications SET job_description = :desc WHERE id = :id"
                ), {'desc': description, 'id': app_id})
                print(f"  Updated description: {company_lower} ({old_desc_len} -> {len(description)} chars)")
            else:
                print(f"  KEPT description: {company_lower} ({old_desc_len} chars already)")

        session.commit()
        print("\nDone! Verifying...")

        # Verify
        rej = session.execute(text(
            "SELECT company, position, "
            "CASE WHEN job_description IS NOT NULL AND LENGTH(job_description) > 0 THEN 'YES' ELSE 'NO' END, "
            "COALESCE(LENGTH(job_description), 0) "
            "FROM applications WHERE status = 'rejected' ORDER BY company"
        )).fetchall()
        print(f"\nRejections ({len(rej)} total):")
        for r in rej:
            print(f"  {r[0]:35s} | {str(r[1])[:40]:40s} | desc={r[2]} | len={r[3]}")


if __name__ == "__main__":
    main()
