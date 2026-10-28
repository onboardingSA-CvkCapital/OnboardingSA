"""Employer pages: which jobs belong to which employer page, and the fixed text written for each page.

The text is written once by hand (no AI at run time). The job list under it is rebuilt every night.
A job belongs to the FIRST group whose pattern matches its employer name.
"""
import re

DPSA_CIRCULAR = "https://www.dpsa.gov.za/newsroom/psvc/"

PUBLIC_SERVICE_APPLY = [
    "Use the current Z83 application form, filled in completely and signed. Applications on the old Z83 (before 2021) are rejected. "
    "Our <a href=\"../guide-z83-form-explained.html\">Z83 guide</a> walks through every section.",
    "Attach a detailed CV. Most departments now ask for certified copies of your ID and qualifications only if you are shortlisted, "
    "but some still want them upfront, so do exactly what the advert says.",
    "Quote the reference number of the post on your Z83. If you apply for two posts, send two separate applications.",
    "Send it the way the advert says: e-mail, online portal, post or hand delivery. The address is different for every post.",
    "Late applications are not accepted, and if you have not heard back within about three months, you can take it that you were not shortlisted.",
]

GROUPS = [
    {
        "slug": "saps-jobs", "short": "SAPS", "name": "South African Police Service",
        "match": r"South African Police Service",
        "logo": "saps",
        "official": ("SAPS careers page", "https://www.saps.gov.za/careers/"),
        "intro": [
            "The South African Police Service (SAPS) is one of the biggest employers in the country, with police stations, "
            "units and offices in every province. Its vacancies fall into two groups, and it helps to know which one you are looking at.",
            "<b>Police Act posts</b> are for police officials: the Police Trainee intake, re-enlistments of former members, and specialised operational posts. "
            "<b>Public Service Act posts</b> are civilian jobs inside SAPS, such as admin clerks, finance, HR, IT, cleaners and drivers. "
            "These are employed under the same rules as other government departments.",
        ],
        "apply": [
            "Police Trainee and some other posts are applied for online on the SAPS e-Recruitment portal, not by e-mail.",
            "Other posts are advertised as PDF adverts on the SAPS careers pages. Each advert says which form to use and where to send it.",
            "Police Trainee applicants go through screening that can include fitness, medical and psychometric assessments. A criminal record or pending case usually rules you out.",
            "Read the age, citizenship and driver's licence requirements carefully. SAPS applies them strictly.",
        ],
        "tips": [
            "SAPS never asks for money to apply, to \"secure a spot\", or for training. Anyone asking is a scammer.",
            "Keep your reference or application number. You will need it if you are called for assessment.",
        ],
    },
    {
        "slug": "eskom-jobs", "short": "Eskom", "name": "Eskom",
        "match": r"^Eskom\b",
        "logo": "Eskom",
        "official": ("Eskom careers portal", "https://eskomcareers.ci.hr/"),
        "intro": [
            "Eskom is South Africa's state-owned electricity utility. It runs the coal-fired power stations in Mpumalanga and Limpopo, "
            "Koeberg nuclear station near Cape Town, and the transmission and distribution network that delivers power across the country.",
            "Most head-office jobs are at Megawatt Park in Sunninghill, Johannesburg. Engineering, artisan and operating posts are at the "
            "power stations and regional offices. Eskom also runs graduate-in-training, apprenticeship and learnership programmes for young people.",
        ],
        "apply": [
            "All Eskom jobs are applied for on the Eskom careers portal. Create a profile once, then apply for each post separately.",
            "Salaries are usually advertised as \"market related\". The grade (for example T12 or M15) tells you the level of the post.",
            "Upload your documents in the format the portal asks for. Incomplete profiles are filtered out automatically.",
            "Many posts close quickly, often within one to two weeks, so apply early.",
        ],
        "tips": [
            "Eskom does not recruit through WhatsApp groups or ask for payment. Only apply through the official portal.",
            "Apprenticeship and graduate posts usually ask for maths and science results, so have your matric certificate ready.",
        ],
    },
    {
        "slug": "sasol-jobs", "short": "Sasol", "name": "Sasol",
        "match": r"^Sasol\b",
        "logo": "Sasol",
        "official": ("Sasol jobs site", "https://jobs.sasol.com"),
        "intro": [
            "Sasol is an energy and chemicals company. Its biggest South African operations are at Secunda in Mpumalanga "
            "and Sasolburg in the Free State, with mining operations around Secunda and offices in Johannesburg.",
            "Typical Sasol vacancies are in engineering, operations, maintenance and artisan trades, mining, safety and health, "
            "and support functions. Sasol also offers learnerships and bursaries for young people.",
        ],
        "apply": [
            "Apply on the Sasol jobs site. You will need to register a profile before you can submit.",
            "Each post lists the minimum qualifications and years of experience. Meet them before applying, because screening is strict.",
            "Learnership adverts often limit applicants to people living near the operation (for example Secunda or Sasolburg). Check the area requirement.",
        ],
        "tips": [
            "Sasol never charges application or training fees. Report anyone who asks.",
            "Keep your CV up to date in your Sasol profile. It is what recruiters see first.",
        ],
    },
    {
        "slug": "correctional-services-jobs", "short": "Correctional Services", "name": "Department of Correctional Services",
        "match": r"^Department of Correctional Services",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "The Department of Correctional Services (DCS) runs correctional centres and community corrections offices across South Africa. "
            "It looks after people in custody and supervises parolees and probationers.",
            "Besides correctional officials, DCS employs nurses, social workers, psychologists, educators, artisans, chefs and admin staff. "
            "Its posts are spread across six management regions and the National Head Office in Pretoria. Many adverts list several "
            "correctional centres for one post, so read the centre list to see where you would work.",
        ],
        "apply": PUBLIC_SERVICE_APPLY,
        "tips": [
            "Posts at centres can be advertised for a specific management area. Apply to the address given for that area.",
            "Some posts need you to pass a fitness or health assessment and a security clearance. Expect background checks.",
        ],
    },
    {
        "slug": "department-of-health-jobs", "short": "Health", "name": "Department of Health",
        "match": r"^Department of Health",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "Public hospitals and clinics are run by the provincial Departments of Health, so each province advertises its own posts. "
            "This page brings together the open posts from all provinces, grouped by province below.",
            "You will find professional nurses, medical officers, pharmacists, radiographers and other health professionals, "
            "plus the admin, finance, porter, cleaning and maintenance staff that keep a hospital running.",
        ],
        "apply": PUBLIC_SERVICE_APPLY + [
            "Health professionals must show proof of registration with their council: SANC for nurses, HPCSA for doctors and most allied "
            "health professions, and SAPC for pharmacy.",
        ],
        "tips": [
            "Health professional salaries follow the OSD (Occupation Specific Dispensation). The grade in the title, such as Grade 1 or Grade 2, depends on your years of experience after registration.",
            "Apply to the hospital or district office named in the advert. It is often not the provincial head office.",
        ],
        "by_province": True,
    },
    {
        "slug": "social-development-jobs", "short": "Social Development", "name": "Department of Social Development",
        "match": r"Social Development",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "The Departments of Social Development deliver welfare services: child protection, care for older persons and people with disabilities, "
            "substance-abuse programmes and support for families in crisis. There is a national department and one in each province.",
            "Most posts are for social workers, social auxiliary workers, child and youth care workers and community development practitioners, "
            "along with the usual admin and finance posts.",
        ],
        "apply": PUBLIC_SERVICE_APPLY + [
            "Social work posts require registration with the South African Council for Social Service Professions (SACSSP). Attach proof if the advert asks.",
        ],
        "tips": [
            "Many posts are at local service offices or facilities, not the head office. Check the centre before you apply.",
        ],
        "by_province": True,
    },
    {
        "slug": "water-and-sanitation-jobs", "short": "Water and Sanitation", "name": "Department of Water and Sanitation",
        "match": r"Water and Sanitation",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "The Department of Water and Sanitation (DWS) manages the country's water resources: dams, bulk water schemes, water quality and water-use licensing. "
            "It has a head office in Pretoria and provincial offices and construction units around the country.",
            "Its vacancies include engineers, scientists, hydrologists, technicians, artisans and construction workers at dam sites, "
            "as well as admin and finance staff.",
        ],
        "apply": PUBLIC_SERVICE_APPLY + [
            "Engineering and science posts usually require professional registration (ECSA for engineers, SACNASP for natural scientists) or candidate status.",
        ],
        "tips": [
            "Construction posts at dam sites are often on contract for the length of a project. Check whether the post is permanent.",
        ],
    },
    {
        "slug": "employment-and-labour-jobs", "short": "Employment and Labour", "name": "Department of Employment and Labour",
        "match": r"Employment and Labour",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "The Department of Employment and Labour enforces labour laws and helps work-seekers and employers. It runs labour centres in towns across the country, "
            "the Unemployment Insurance Fund (UIF) and the Compensation Fund.",
            "Common posts are labour inspectors, employment services practitioners, client service officers at labour centres, "
            "and claims and finance staff for UIF and the Compensation Fund.",
        ],
        "apply": PUBLIC_SERVICE_APPLY,
        "tips": [
            "Posts at labour centres are advertised per town. Apply to the provincial office named in the advert.",
            "Inspector posts usually ask for a valid driver's licence because the work involves travel to workplaces.",
        ],
    },
    {
        "slug": "higher-education-and-training-jobs", "short": "Higher Education and Training", "name": "Department of Higher Education and Training",
        "match": r"Higher Education and Training",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "The Department of Higher Education and Training (DHET) oversees universities, TVET colleges and Community Education and Training (CET) colleges.",
            "Many of its adverts are for posts at TVET and CET colleges: lecturers, campus managers, student support officers and admin staff. "
            "There are also head office posts in Pretoria.",
        ],
        "apply": PUBLIC_SERVICE_APPLY,
        "tips": [
            "College posts are applied for at the college's own address, which differs for each campus.",
            "Lecturer posts list the subject and the qualification you need in it. Match both before you apply.",
        ],
    },
    {
        "slug": "land-reform-and-rural-development-jobs", "short": "Land Reform and Rural Development",
        "name": "Department of Land Reform and Rural Development",
        "match": r"Land Reform and Rural Development",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "The Department of Land Reform and Rural Development handles land restitution, redistribution and tenure reform, "
            "deeds registration, surveys and mapping, and rural development programmes.",
            "Posts range from land surveyors, GIS and deeds examiners to development facilitators and admin staff, "
            "at the head office in Pretoria and at provincial and district offices.",
        ],
        "apply": PUBLIC_SERVICE_APPLY,
        "tips": [
            "Surveying and GIS posts often require registration with the relevant professional council. Check the requirements line.",
        ],
    },
    {
        "slug": "gauteng-infrastructure-development-jobs", "short": "Gauteng Infrastructure Development",
        "name": "Gauteng Department of Infrastructure Development",
        "match": r"^Department of Infrastructure Development \(Gauteng\)",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "The Gauteng Department of Infrastructure Development builds and maintains provincial government buildings such as schools, "
            "clinics, hospitals and offices, and manages the province's property portfolio.",
            "Its vacancies lean towards the built environment (engineers, architects, quantity surveyors, project managers and artisans), "
            "plus property management, supply chain and admin posts.",
        ],
        "apply": PUBLIC_SERVICE_APPLY + [
            "Professional built-environment posts usually require registration with ECSA, SACAP or SACPCMP. Attach proof.",
        ],
        "tips": [
            "This department often advertises many posts at once. Use the reference numbers to keep your applications apart.",
        ],
    },
    {
        "slug": "gauteng-community-safety-jobs", "short": "Gauteng Community Safety", "name": "Gauteng Department of Community Safety",
        "match": r"^Department of Community Safety \(Gauteng\)",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "The Gauteng Department of Community Safety oversees policing in the province and runs crime-prevention programmes. "
            "It is also home to the Gauteng Traffic Police.",
            "That makes it one of the main places to find traffic officer and traffic management posts in Gauteng, "
            "along with safety promotion, monitoring and admin posts.",
        ],
        "apply": PUBLIC_SERVICE_APPLY + [
            "Traffic officer posts usually require a valid driver's licence and may require a traffic officer diploma or training. Read the requirements line.",
        ],
        "tips": [
            "Traffic posts can involve shift work, weekends and public holidays.",
        ],
    },
    {
        "slug": "public-works-and-roads-jobs", "short": "Public Works and Roads", "name": "Public Works, Roads and Transport departments",
        "match": r"Public Works|Roads and Transport|Roads and Infrastructure",
        "logo": "government",
        "official": ("DPSA Public Service Vacancy Circular", DPSA_CIRCULAR),
        "intro": [
            "Public works and roads departments maintain government buildings and provincial roads, and many also run public transport and driver licensing services. "
            "This page brings together the national Department of Public Works and Infrastructure and the provincial public works, roads and transport departments.",
            "Expect posts for engineers and technicians, artisans and road workers, building maintenance staff, "
            "and the admin, finance and supply chain staff behind them.",
        ],
        "apply": PUBLIC_SERVICE_APPLY,
        "tips": [
            "Roads and maintenance posts are often based at district depots, not the head office. Check the centre before you apply.",
        ],
        "by_province": True,
    },
]

for g in GROUPS:
    g["rx"] = re.compile(g["match"], re.I)


def group_for(employer):
    """The employer page a job belongs to (dict), or None."""
    for g in GROUPS:
        if g["rx"].search(employer or ""):
            return g
    return None
