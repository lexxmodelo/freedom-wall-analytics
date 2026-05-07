**AI-Driven Topic Modeling and Multidimensional Sentiment Analysis of**

**Student Discourse on selected Philippine University Freedom Walls.**

```
Thesis Proposal
Presented to the Faculty of the
School of Accountancy, Management, Computing and Information Studies
SAINT LOUIS UNIVERSITY
Baguio City
```
```
Submitted By:
```
```
Albarida, Ivan A.
Saint Louis University
Maryheights Campus, Bakakeng,
2600 Baguio City, Philippines
Department of Computer Science
2233471@slu.edu.ph
Gapuz, Emil John C.
Saint Louis University
Maryheights Campus, Bakakeng,
2600 Baguio City, Philippines
Department of Computer Science
2233372@slu.edu.ph
```
```
Burgos, Miguel Joshua
Saint Louis University
Maryheights Campus, Bakakeng,
2600 Baguio City, Philippines
Department of Computer Science
2233004@slu.edu.ph
Llena, Anthony
Saint Louis University
Maryheights Campus, Bakakeng,
2600 Baguio City, Philippines
Department of Computer Science
2235774@slu.edu.ph
```
```
Calera, Earl Daniele S.
Saint Louis University
Maryheights Campus, Bakakeng,
2600 Baguio City, Philippines
Department of Computer Science
2232890@slu.edu.ph
Modelo, Alexx Evan O.
Saint Louis University
Maryheights Campus, Bakakeng,
2600 Baguio City, Philippines
Department of Computer Science
2232978@slu.edu.ph
Salda, Jayson S.
Saint Louis University
Maryheights Campus, Bakakeng,
2600 Baguio City, Philippines
Department of Computer Science
2233081@slu.edu.ph
```
```
Viduya, Hans Elijah
Saint Louis University
Maryheights Campus, Bakakeng,
2600 Baguio City, Philippines
Department of Computer Science
2233053@slu.edu.ph
```
```
Submitted to:
Dr. Josephine Dela Cruz
Submitted on:
December 14, 2025
```

## TABLE OF CONTENTS


- 1. Introduction..............................................................................................................................................
   - 1.1 Background of the Study...................................................................................................................
   - 1.2 Statement of the Problem..................................................................................................................
   - 1.3 Objectives of the Study......................................................................................................................
      - 1.3.1 General Objective....................................................................................................................
      - 1.3.2 Specific Objectives..................................................................................................................
   - 1.4 Research Framework.........................................................................................................................
      - 1.4.1 Input Phase...............................................................................................................................
      - 1.4.2 Process Phase...........................................................................................................................
      - 1.4.3 Output Phase............................................................................................................................
   - 1.5 Significance of the Study...................................................................................................................
   - 1.6 Scope and Delimitations....................................................................................................................
   - 1.7 Definition of Terms..........................................................................................................................
- 2. Review of Related Literature................................................................................................................
   - 2.1 The Sociology of the Digital Confessional......................................................................................
   - 2.2 The Linguistic Challenge.................................................................................................................
   - 2.3 Evolution of Topic Modeling...........................................................................................................
   - 2.4 The Paradigm Shift in Sentiment Analysis......................................................................................
   - 2.5 Ethical Frameworks and Data Privacy............................................................................................
   - 2.6 Synthesis of the Reviewed Literature..............................................................................................
   - 2.7 Framework.......................................................................................................................................
      - 2.7.1 Theoretical Framework..........................................................................................................
      - 2.7.2 Conceptual Framework..........................................................................................................
- 3. Design and Methods...............................................................................................................................
   - 3.1 Research Design..............................................................................................................................
   - 3.2 Data Collection................................................................................................................................
   - 3.3 Preprocessing...................................................................................................................................
      - 3.3.1 Field Selection and Structural Filtering.................................................................................
      - 3.3.2 Numeric and Engagement Normalization..............................................................................
      - 3.3.3 Noise Reduction and Regex Cleaning...................................................................................
      - 3.3.4 Linguistic Preservation and Tokenization..............................................................................
      - 3.3.5 Context-Aware Stopword Removal.......................................................................................
      - 3.3.6 Academic Unit Categorization...............................................................................................
      - 3.3.7 Output Serialization...............................................................................................................
   - 3.4 Topic Modeling................................................................................................................................
   - 3.5 Topic Labeling and Hallucination Control......................................................................................
      - 3.5.1 Integration Architecture.........................................................................................................
      - 3.5.2 Input Selection Strategy.........................................................................................................
      - 3.5.3 Prompt Engineering...............................................................................................................
      - 3.5.4 Hallucination Mitigation Protocols........................................................................................
   - 3.6 Sentiment Analysis..........................................................................................................................
      - 3.6.1 The Hybrid Inference Architecture........................................................................................
      - 3.6.2 Prompt Engineering for VAD Quantification........................................................................
      - 3.6.3 Sarcasm Detection Protocol...................................................................................................
      - 3.6.4 Data Balancing and Augmentation........................................................................................
   - 3.7 Validation Strategy (Human-in-the-Loop).......................................................................................
   - 3.8 Tool Development and System Architecture...................................................................................
   - 3.9 Ethical Considerations and Limitations...........................................................................................
      - 3.9.1 Data Minimization Protocol...................................................................................................
      - 3.9.2 Anonymization Pipeline.........................................................................................................
      - 3.9.3 Data Storage and Security Protocol.......................................................................................
      - 3.9.4 “Do No Harm” Trigger Protocol............................................................................................
   - 3.10 Summary of Methodology.............................................................................................................
- References...................................................................................................................................................
- Annexes.......................................................................................................................................................
   - ANNEX A : Proof of Concept and Pilot Study Results........................................................................


## 1. Introduction..............................................................................................................................................

### 1.1 Background of the Study...................................................................................................................

In the Philippines, digital technology and social media have become a regular part of daily life. Studies
show that Internet use in the country is high. Filipinos regularly surpass global averages for daily Internet
and social media usage (We Are Social & Hootsuite, 2019). Since mobile phones were introduced in the
early 1990s, researchers have highlighted the vital role of these technologies, especially text messaging, in
shaping social communication in the Philippines (Ellwood-Clayton, 2003; Pertierra, 2005; Uy-Tioco,
2019).

As these technologies have become widespread, student interactions have increasingly moved from
traditional physical spaces to digital environments. This change reflects a broader shift in social
interaction, where the lines between private feelings and public expression are often unclear. Historically,
university life relied on physical locations where expressing grievances was limited by institutional
hierarchies. While universities have set up official digital channels, such as Learning Management
Systems and student council pages, many students see these spaces as monitored or overly formal. As a
result, discussions have shifted to anonymous digital platforms known as 'Freedom Walls.' These pages
have emerged as important, though unofficial, spaces for expression, especially within the University
Athletic Association of the Philippines (UAAP) network. The anonymity allows students to share honest
opinions on sensitive issues, including academic stress and institutional grievances, that they might
otherwise censor on official channels.

The nature of this digital communication marks a significant change from traditional feedback methods.
Conventional student feedback, gathered through end-of-term evaluations or formal surveys, is often
infrequent and can suffer from response bias or sanitization by the time it reaches decision-makers (Shah
et al., 2017). In contrast, the discussions on Freedom Walls are continuous, real-time, and unfiltered.
Hayat et al. (2024) describe modern student feedback as a type of big data that lacks structure. It creates a
chaotic mix of academic commentary, campus politics, and social interactions among students in a single
stream. This shows that student experiences are now documented not just in organized reports but also in
the fast-paced environment of social media. The global COVID-19 pandemic sped up this digital reliance.
Alkhnbashi and Nassr (2023) noted that during the transition to online and hybrid learning, student
concerns mostly shifted to digital spaces due to the absence of physical options. At one point, the
Freedom Wall became the main place for interaction. Concerns about internet issues, feelings of isolation,
and disconnect from teaching methods were voiced online, creating a feedback collection that was often
more immediate than formal evaluations. Even as universities resumed face-to-face classes, the pattern of
digital expression has persisted.

This digital shift has resulted in a communication "shadow infrastructure" that operates outside university
administration control. In the hierarchical structure of Philippine universities, students often hesitate to
raise concerns face-to-face due to cultural norms or fear of academic consequences. The digital
environment removes these obstacles. Anonymity allows a freshman to openly criticize a senior professor
or university policies with the same visibility as any other stakeholder. This leads to critical discussions
about the university occurring in a space where the administration is just a spectator. Such a disconnect


poses a governance challenge, as institutions might miss the real state of student feelings if they depend
solely on traditional methods. This situation has created a dilemma where universities must deal with a
parallel institution they cannot control. Unlike official feedback methods, which are often slow and
bureaucratic, the Freedom Wall offers prompt communication. For a student facing a crisis, the official
complaint process can seem overwhelming and sluggish, while the Freedom Wall provides an immediate
audience.

As Soriano et al. (2025) indicate, the Freedom Wall has effectively become the go-to "first responder" for
student concerns. When something goes wrong or a policy is confusing, reports typically surface on social
media hours or days before reaching a university administrator. This makes the Freedom Wall a critical,
though unmanaged, part of the university’s information landscape. The presence of this shadow
infrastructure suggests that the university's understanding of student sentiment may lag behind the reality
reflected on these unofficial platforms. While the Freedom Wall serves as a necessary outlet for students,
it also represents a tricky variable for university management. For the administration, these platforms
create a governance gap that reduces their control over the institutional narrative. Gracia et al. (2025)
emphasize the tension between public visibility and security, noting that social media often becomes a
space for privacy violations without formal oversight. Unlike internal complaint mechanisms, which keep
grievances confidential, the Freedom Wall publicly broadcasts allegations to parents, alumni, and
prospective students.

This openness creates a high-stakes situation of unmoderated public judgement, where unproven claims
about faculty misconduct or safety issues can quickly gain traction. Pangilinan et al. (2021) describe this
phenomenon as digital gossip that challenges existing power dynamics. The damaging effects can be
immediate, potentially harming trust among stakeholders before the institution has a chance to investigate
the claims.

The operational risk is heightened by the speed of information flow on social media compared to the
slower pace of university decision-making. Alexander et al. (2019) caution that social media algorithms
can amplify outrage, allowing speculation about tuition increases or misunderstood policies to escalate
into campus-wide controversies very quickly. In contrast, official university responses usually require
verification and approval. By the time an official clarification is issued, the narrative on the Freedom Wall
may have already taken shape, leading to a power vacuum where unofficial information becomes the
dominant truth for students. Moreover, university administrators frequently find themselves limited in
handling these platforms. Because Freedom Walls are typically run by students and hosted on third-party
sites like Facebook, the university lacks the authority to delete posts or identify authors. They essentially
act as observers. Since censorship is not possible, Hayat et al. (2024) recommend that the only effective
response is automated analysis. Administrators need tools to spot early signs of public relations crises or
safety threats before they worsen. Currently, the wealth of unfiltered feedback on Freedom Walls rarely
receives systematic responses from the institution.

Universities generally approach this issue with ineffective strategies. The first is to ignore these platforms,
deeming the content unproductive gossip outside their responsibility. The second is manual monitoring,
where staff try to check content post by post—a method that Soriano et al. (2025) point out is not feasible


given the vast number of posts each semester. Currently, institutional monitoring largely relies on native
platform analytics (e.g., Meta Business Suite) that track engagement on official university pages.
However, these tools cannot access the 'shadow infrastructure' of unofficial Freedom Walls, as
administrators lack the necessary access to pull data from these third-party pages. While basic monitoring
tools like Google Alerts are sometimes used, they depend on rigid keyword matching, which does not
capture the nuance of code-switched (Taglish) narratives. As a result, critical posts often remain unnoticed
until they escalate into crises. Moreover, human interpretation during manual reviews is subjective, as
readers carry personal biases into the evaluation process. This method is prone to delays. Important posts
can stay hidden for long periods, and discovering issues after the critical moment has passed makes
effective intervention difficult. These limitations indicate that current failures stem from insufficient
technological resources rather than a lack of commitment from institutions. Universities need dedicated
tools to manage the huge flow of unstructured student feedback. Without such tools, institutions can
struggle to fully hear student opinions or identify crucial information lost in the noise.

Given these constraints, the main issue is the necessity to break the cycle of reactive management and low
institutional awareness. Transitioning from anecdotal observation to empirical, automated measurement is
essential. The sheer volume of student interactions on social media calls for a technological solution that
can handle high volumes of unstructured text quickly. Hayat et al. (2024) argue that in this era of constant
digital feedback, anecdotal evidence is insufficient for policy decisions; institutions need consistent,
data-driven insights. By implementing an AI-driven framework, the university can standardize how
student sentiment is interpreted. This effectively eliminates the human bias and bureaucratic delays
affecting current monitoring efforts. This transition allows the Freedom Wall to change from a chaotic
liability into a structured resource for institutional knowledge, helping decision-makers identify systemic
issues based on facts rather than guesswork.

To accomplish these changes, the proposed system makes use of two basic computational techniques:
Sentiment Analysis to measure the emotional intensity of those themes and Topic Modeling to identify the
underlying themes of student discourse. When combined, these technologies offer the scalability needed
to create a cohesive story of the student experience from thousands of disparate posts. But there are a lot
of obstacles to overcome before such a system can be implemented in the Philippine setting. Standard AI
models frequently fall short in addressing the particular challenges posed by the data's linguistic and
structural features.

### 1.2 Statement of the Problem..................................................................................................................

The primary issue is the crucial informational imbalance between the student body's broad, unstructured
digital discourse and university administrations' restricted, manual monitoring capabilities. A "shadow
infrastructure" of communication has developed as student expression shifts to anonymous "Freedom
Walls," which function more quickly than conventional institutional feedback systems. The volume and
language complexity of this data are too much for current manual governance techniques to handle, which
leads to a systemic failure to translate digital student sentiment into useful institutional intelligence. Thus,
three crucial failures result from this epistemic gap:


```
● Operational Blindness : University administrators cannot manually process thousands of
unstructured posts, causing significant delays in identifying emerging crises or systemic
grievances.
● Analytical Inaccuracy : Traditional NLP tools fail to parse the semantic nuance of informal
Filipino–English code-switching (Taglish), leading to misclassification of student sentiment and
intent.
● Governance Disconnect : Vital patterns regarding mental health and campus safety remain
invisible, forcing institutions to rely on reactive anecdotal evidence rather than proactive
data-driven insights.
```
### 1.3 Objectives of the Study......................................................................................................................

#### 1.3.1 General Objective....................................................................................................................

To develop an automated, AI-driven analytical framework that extracts, clusters, and quantifies dominant
themes and multidimensional emotional landscapes from student-generated Freedom Wall posts across
selected Philippine Higher Education Institutions.

#### 1.3.2 Specific Objectives..................................................................................................................

1. To **harvest and curate** a large-scale corpus of unstructured Freedom Wall posts from selected
    UAAP and State Universities, utilizing context-aware filtration to handle code-switched (Taglish)
    noise effectively.
2. To implement a **Transformer-based Topic Modeling architecture** (BERTopic) to discover latent
    semantic themes and categorize student discourse beyond surface-level keywords.
3. To deploy a **Hybrid Valence-Arousal-Dominance (VAD) utilizing Few-Shot Prompting on**
    **Large Language Models (LLMs)** sentiment engine utilizing Generative AI to quantify the
    intensity and agency of student emotion within informal text.
4. To evaluate the **semantic coherence** and classification accuracy of the proposed AI models using
    a rigorous Human-in-the-Loop (HITL) validation protocol.
5. To **synthesize** the analytical results into an **interactive visualization dashboard** that translates
    technical vectors into actionable institutional intelligence, enabling real-time topic evolution and
    emotional trajectories for administrative decision-making.

### 1.4 Research Framework.........................................................................................................................

The research framework outlines how unstructured social media data is transformed into
structured, actionable intelligence. Rooted in Computational Social Science, the study uses an
Input-Process-Output (IPO) model to show how raw digital conversations are collected, analyzed through
advanced Natural Language Processing (NLP), and turned into useful insights for university governance.


#### 1.4.1 Input Phase...............................................................................................................................

The input phase focuses on the raw, unstructured student discussions gathered from the public
Freedom Walls of selected Philippine higher education institutions. This data represents a massive,
linguistically complex stream of communication characterized by anonymity and the frequent use of
Taglish. Rather than just viewing these posts as casual interactions, this phase treats them as a rich
collection of hidden student sentiments and feedback waiting to be uncovered. The data is carefully
aggregated to ensure that privacy and data-minimization principles are strictly followed.

#### 1.4.2 Process Phase...........................................................................................................................

The process phase serves as the analytical engine that converts this raw text into structured data.
It relies on a two-part NLP approach. First, Topic Modeling is used to uncover the hidden thematic
clusters within student discussions. Second, Multidimensional Sentiment Analysis measures the
emotional intensity and agency, specifically Valence, Arousal, and Dominance, connected to those
themes. To handle the nuances of local dialects, the process includes linguistic preprocessing. This
ensures that the true semantic meaning of student expressions is maintained and accurately categorized
during computational analysis.

#### 1.4.3 Output Phase............................................................................................................................

Finally, the output phase brings the processed data together into an interactive visualization
dashboard. This tool translates complex computational metrics into easy-to-understand thematic maps and
emotional trends. By showing how specific campus issues relate to real-time student feelings, the
framework gives administrators the concrete evidence they need to create proactive policies and targeted
interventions. Ultimately, this bridges the critical gap between the actual student experience and
institutional awareness.

### 1.5 Significance of the Study...................................................................................................................

This study addresses the operational divide between the chaotic volume of digital student
discussions and the structured information needed for effective university governance. By turning the
unstructured noise of social media into reliable intelligence, this research creates a framework for
responsive administration in the digital age. It encourages institutions to shift from simply reacting to
issues to proactively managing them, ensuring that university policies are shaped by the lived reality of
students rather than delayed formal reports. This transformation holds specific significance for several
key stakeholders.

For **university administrators** , particularly within the UAAP network and state universities, this
research offers a much-needed technological upgrade to their current monitoring capabilities. In large
institutions with tens of thousands of students, manually tracking student sentiment is logistically
impossible. This proposed tool transforms the Freedom Wall from a potential public relations liability into
a valuable source of empirical data. It provides decision-makers in high-stakes environments with a
scalable early warning system. This allows them to spot areas of friction, such as enrollment failures,
safety threats, or growing mental health crises, before they escalate into public controversies. While the


tool itself may not fix these deep-rooted structural issues, it equips administrators with the accurate
diagnosis needed to allocate resources effectively and draft policies that address the real, rather than
presumed, needs of the campus.

For the **student body** , this study validates the role of their digital expressions as a crucial safety
valve. Because the analysis does not require exposing personal identities, the research brings this shadow
discourse into the light of administrative awareness without compromising student anonymity. This is an
indirect but essential benefit, as unfiltered student feedback is systematically processed instead of being
dismissed as mere noise. It paves the way for more responsive institutional support structures, particularly
regarding mental health and student welfare. Concerns raised safely behind a screen can now translate
into tangible improvements in the physical campus environment, completely free from the fear of
academic retaliation.

Furthermore, this research contributes significantly to the field of **Natural Language Processing
(NLP)** by advancing low-resource language modeling. There is currently a lack of high-quality datasets
and models for Taglish, a complex code-switched language that Western AI tools often fail to process
accurately. By demonstrating that multilingual transformers and hybrid scoring methods are effective for
Philippine social media texts, this study provides a reliable pipeline for handling informal
Filipino-English discourse. The annotated datasets and fine-tuned models created here can serve as
foundational materials for future linguistic research in the Philippine context.

Finally, for **future researchers** , this paper offers a replicable method for studying the concept of
shadow infrastructures in education. As student conversations increasingly move toward decentralized
online platforms, researchers can use the techniques developed in this study, combining advanced
clustering with generative AI labeling, to explore new areas of public discourse. This research acts as a
roadmap for applying ethical AI to sensitive, publicly driven information, striking a necessary balance
between the need for social observation and the strict requirements of data protection.

### 1.6 Scope and Delimitations....................................................................................................................

This research focuses on the online shadow systems of Philippine higher education institutions,
specifically examining the Freedom Wall pages of selected universities. It looks at data from recent
academic semesters to identify seasonal trends in student conversations. The analysis is strictly limited to
publicly available text posts written in English, Filipino, or Taglish. Multimedia content, such as memes,
screenshots, and videos, as well as comment sections, are excluded from the study. These elements
introduce a level of complexity that requires a different type of analysis outside the scope of this research.
While it is recognized that excluding multimedia means missing out on the visual humor and
context-heavy irony often found in memes, the study intentionally prioritizes core textual expression. It is
within these text posts that students most directly articulate their feelings and concerns. Comment sections
are also omitted, primarily for ethical reasons, as they frequently contain identifiable responses that could
compromise privacy. Moreover, discussions in the comments often drift away from the original
anonymous post, making them a less reliable source for tracking core trends in student sentiment.


The study looks closely at the Freedom Wall pages of twelve institutions chosen based on three criteria:
(1) High Volume Activity, meaning pages that produce at least 4,000 posts each semester; (2) Regional
Representation, which ensures a balance between Metro Manila and provincial institutions; and (3)
Institutional Diversity, including State Universities, Private Sectarian schools, and Private Non-Sectarian
schools.

The selected institutions are categorized as follows:

1. **Metro Manila Cluster:** University of the Philippines Diliman (UPD), De La Salle University
    (DLSU), Ateneo de    University (ADMU), Far Eastern University (FEU), and Polytechnic
    University of the Philippines (PUP) Sta. Mesa.
2. **Luzon/Provincial Cluster:** University of the Philippines Los Baños (UPLB), Lyceum of the
    Philippines University Batangas (LPU-B), and Caraga State University (CSU).
3. **Baguio/Benguet Cluster** : University of the Philippines Baguio (UPB), Benguet State University
    (BSU), and University of Baguio (UB)."

The selected institutions include provincial universities, such as BSU, UB, and CSU. This study focuses
on Tagalog, English, and Taglish discourse. Posts that are mostly written in regional dialects, like Ilokano
and Kapampangan, will be removed during the preprocessing stage. The current transformer models,
including RoBERTa-Tagalog, are not pre-trained on these low-resource regional languages. This helps
maintain the semantic stability of the embeddings.

The study is limited to aggregate level analysis in terms of methodology. It does topic modeling and
emotion scoring on group trends, but it doesn't try to figure out who wrote something, what their mental
state was, or how true any confession was. The AI models can find patterns in language and emotions, but
they can't tell if claims are true or diagnose mental illnesses. In this way, the results show how the
students felt, but they don't objectively review how well the institution did.

The study is aware of the limits of NLP when it comes to the quickly changing internet slang and the new
slangs. Even though multilingual transformers make it easier to process code switching, it might be hard
to put some new phrases into groups. The dashboard that comes out of this is only used as a
decision-support tool, and it works on scheduled batch processing, which means there is some latency. It
provides retrospective insights on policy planning rather than immediate crisis alerts and is intended to
enhance, rather than replace, formal feedback mechanisms and the professional judgments of
administrators and guidance counselors.

### 1.7 Definition of Terms..........................................................................................................................

The following terms are defined conceptually and operationally to ensure clarity and a common
understanding within the context of this study.

1. Term: **Arousal**
    a. **Conceptual Definition:** A dimension of emotion representing the state of being awoken
       or stimulated, ranging from low activation (sleepiness/calm) to high activation
       (excitement/panic) (Russell, 1980).


```
b. Operational Definition: In this study, it is a numerical score (scale 1–9) used to
distinguish between "Passive" negative emotions (e.g., burnout/boredom) and "Active"
negative emotions (e.g., anger/rage), serving as a proxy for urgency.
```
2. Term: **BERTopic**
    a. **Conceptual Definition:** A modular topic modeling technique that leverages
       transformer-based embeddings and class-based TF-IDF (c-TF-IDF) to create dense,
       coherent clusters from short-text data (Grootendorst, 2022).
    b. **Operational Definition:** In this study, it is the specific algorithm configured with the
       “paraphrase-multilingual-MiniLM-L12-v2” embedding model and HDBSCAN clustering
       used to overcome the "data sparsity" limitations of traditional LDA on Facebook posts.
3. Term: **Dominance**
    a. **Conceptual Definition:** A dimension of emotion representing the degree of control or
       agency an individual feels over their environment or situation (Russell, 1980; Panadero,
       2022).
    b. **Operational Definition:** In this study, it is a numerical score (scale 1–9) indicating
       whether the student author feels helpless/victimized (Low Dominance) or
       empowered/in-control (High Dominance) regarding the issue they are posting about.
4. Term: **Freedom Wall (HEI Version)**
    a. **Conceptual Definition:** An anonymous, crowd-sourced social media page managed by
       third-party administrators, often students, which serves as a venue for "interactive
       discussions" and emotional expression within a specific community (Balabag & Potane,
       2024).
    b. **Operational Definition:** In this study, it refers specifically to the publicly accessible
       Facebook Pages (excluding Private Groups) associated with the selected HEIs from
       which the unstructured textual dataset (confessions, rants, and feedback) is harvested
       using the Apify scraping tool.
5. Term: **Human-in-the-Loop (HITL)**
    a. **Conceptual Definition:** A model validation methodology where human agents interact
       with the algorithmic loop to review, validate, or correct the system's output to improve
       accuracy (Monarch, 2021).
    b. **Operational Definition:** In this study, it refers to the validation protocol where eight
       human annotators review a stratified 5% sample of the AI's output using the Label Studio
       interface to calculate Inter-Rater Reliability metrics.
6. Term: **Institutional Latency**
    a. **Conceptual Definition:** The time delay between the occurrence of an event or the
       generation of data and the organizational awareness or response to that data (Soriano et
       al., 2025).


```
b. Operational Definition: In this study, it refers to the operational gap between a student
posting a grievance on the Freedom Wall and the university administration detecting it,
which the proposed automated dashboard aims to minimize from days/weeks to 24 hours.
```
7. Term: **Online Disinhibition Effect**
    a. **Conceptual Definition:** A psychological phenomenon where the anonymity and
       invisibility of the internet reduce social restraints, leading individuals to express
       themselves more openly—either benignly or toxically—than in face-to-face interactions
       (Suler, 2004).
    b. **Operational Definition:** In this study, this term refers to the underlying psychological
       mechanism that generates the "high-variance" and "high-intensity" nature of the Freedom
       Wall dataset, validating the need for automated toxicity detection.
8. Term: **Taglish**
    a. **Conceptual Definition:** A form of intrasentential code-switching that blends Tagalog
       and English morphology and syntax, serving as a complex linguistic register used by
       bilinguals to facilitate vocabulary bridging and emotional expression (Manuel, 2024;
       Anacin, 2022).
    b. **Operational Definition:** In this study, Taglish refers to the primary language of the
       dataset, characterized by non-standard spelling and mixed grammar, which necessitates
       the use of the specific "No-Translation" preprocessing pipeline and multilingual
       transformer models.
9. Term: **Topic Modelling**
    a. **Conceptual Definition:** An unsupervised machine learning technique used to scan a set
       of documents, detect word and phrase patterns, and automatically cluster them into
       abstract "topics" that characterize the dataset (Blei et al., 2003).
    b. **Operational Definition:** In this study, it refers to the computational process performed
       by the BERTopic architecture to categorize thousands of unstructured student posts into
       labeled themes (e.g., "Academic Stress," "Enrollment Issues") without manual coding.
10. Term: **Valence**
    a. **Conceptual Definition:** A dimension of emotion representing the intrinsic attractiveness
       or aversiveness of an event, object, or situation, ranging from unpleasant to pleasant
       (Russell, 1980).
    b. **Operational Definition:** In this study, it is a numerical score (scale 1–9) indicating
       whether a student post is negative (e.g., sadness, disappointment) or positive (e.g.,
       gratitude, joy).


## 2. Review of Related Literature................................................................................................................

The use of social media has changed how students communicate in universities. It turned the
Freedom Wall from a simple online trend into a major platform where students share secrets, complain,
and express their feelings instantly. This change creates a unique problem. While these pages provide a
huge amount of student feedback, the messy mix of languages, slang, and strong emotions makes it hard
for administrators to understand the content using standard monitoring methods. To connect this
unorganized data with useful information for the university, a combined approach using sociology,
language studies, and data science is needed.

This review looks at the ideas and technology required to build an automated AI system for this
task. It starts by explaining the social purpose of online confessions. Then, it discusses the language
challenges of Philippine Taglish, which often limit the effectiveness of standard Western AI tools.
Following this, the review outlines the shift from older text analysis methods like Latent Dirichlet
Allocation (LDA) to newer BERTopic models. Finally, it explains the need to move away from simple
positive or negative sentiment tracking toward a more detailed mapping of student emotions.

### 2.1 The Sociology of the Digital Confessional......................................................................................

As student conversations move from physical spaces to online platforms, pages like the University
Freedom Wall have become important social spaces. These anonymous areas act as both public diaries
and places for debate. They blur the line between private feelings and public reading (Balabag & Potane,
2024). In practice, they use a double-blind system through tools like Google Forms or Secreto. This
ensures that neither the public nor the student administrators know who wrote the post. Townsend and
Wallace (2016) point out that this setup creates an ethical dilemma. It encourages users to share sensitive
stories about school rules and campus life in spaces that are actually public.

Socially, Freedom Walls act as safety valves for student well-being. In the Philippines, cultural values like
“ _pakikisama_ ” or social harmony often stop people from complaining directly. The platform lets students
share their worries without fearing social or academic punishment (Montefalcon et al., 2023; Rodriguez et
al., 2023). Being anonymous encourages a harmless type of openness known as benign disinhibition
(Suler, 2004). It allows students to criticize authority figures or talk about their personal struggles freely.

However, this same hidden identity can lead to toxic behavior. It produces angry interactions and digital
gossip that can quickly turn into online mobs (Pangilinan et al., 2021). Unproven claims can spread fast.
This creates risks for the university and can damage reputations before a proper investigation happens
(Tabloid Editorial Board, 2025).

Aside from these social factors, the high number of student posts creates practical problems. Checking
posts by hand is no longer realistic. A single semester can produce thousands of updates. This creates a
blind spot for the administration, where signs of mental health issues or important feedback get lost in the
noise (Soriano et al., 2025; Hayat et al., 2024; Albarida et al., 2025). The huge amount and complex
nature of these posts show a flaw in current monitoring methods. This highlights the need for a solution
based on data that can handle large volumes of text.


Even though the Freedom Wall is important for student expression, its busy and complex nature
overwhelms manual tracking. This puts both student well-being and the university's reputation at risk.
There is a strong need for an organized, AI-assisted method to collect, analyze, and respond to student
feedback effectively.

### 2.2 The Linguistic Challenge.................................................................................................................

A major challenge in automating the analysis of Philippine Freedom Walls is the complex
language of Taglish. Rather than being a random mix of words, Anacin (2022) explains that this
code-switching follows specific rules. Manuel (2024) points out that this mixing has a clear purpose.
Students often use English for technical terms, while they use Tagalog to show strong emotions, like in
the word " _nakaka-stress_ ." Because mixing these languages carries important meaning, simply translating
the text into English is a poor approach. It removes the emotional context needed for an accurate
sentiment analysis.

Keeping the text in its original form creates a problem for standard Western AI tools. Abisado et al.
(2023) note that basic models like VADER fail because they only rely on English dictionaries. As a result,
culturally specific words with strong feelings, like " _sayang_ " or " _gigil_ ," are often mistakenly marked as
neutral (Cabasag et al., 2025). Furthermore, the way Tagalog words change meaning by adding prefixes
or suffixes, such as "nag-aral" versus "mag-aaral," confuses standard computer algorithms. This stops the
system from seeing the connections between related words, leading to a flawed analysis.

To solve these issues, research suggests using advanced multilingual models. Cruz and Cheng (2021) set
the standard in the Philippines with RoBERTa-Tagalog. This model is specially trained to recognize
Tagalog root words and context. Cosme and De Leon (2024) supported this approach, showing that
multilingual models like XLM-RoBERTa perform much better than English-only versions when reading
mixed-language text. By looking at the context of the words instead of relying on direct translations or
strict dictionaries, these models keep both the structure and the emotional meaning of Taglish intact.

Ultimately, the complex nature of Taglish makes standard sentiment analysis tools ineffective. This
creates a gap in truly understanding student conversations on Freedom Walls. It highlights the absolute
need for AI methods that preserve the exact structure and emotional details of the original posts.

### 2.3 Evolution of Topic Modeling...........................................................................................................

Automated categorization of thousands of unstructured Freedom Wall posts requires a shift from
traditional statistical methods to semantic artificial intelligence. For over a decade, Latent Dirichlet
Allocation (LDA) served as the standard, operating on a Bag-of-Words assumption that counts word
co-occurrences to identify patterns (ThirdEye Data Team, 2025). However, Egger et al. (2022) argue that
this methodology fails when applied to social media. Freedom Wall posts are often short-text data
characterized by brevity and noise. In this context, LDA suffers from data sparsity. Because it relies
strictly on word counts, it cannot recognize context, often producing incoherent topics where semantically
related terms, such as "prof" and "instructor," are not grouped together.


Transformer-based architectures such as BERTopic have been adopted to overcome these limitations.
George et al. (2023) explain that instead of counting words, BERTopic uses semantic embeddings to map
words as vectors in a geometric space, allowing the model to understand context and synonymy. Sy et al.
(2024) empirically validated this approach in the Philippine context, demonstrating that BERTopic
achieved significantly higher semantic coherence than LDA when analyzing student feedback on tuition
policies. Additionally, Khodeir (2025) highlights that this architecture excels at identifying urgent topics
in online forums because it leverages pre-trained Large Language Models to interpret vague or coded
language that statistical models miss.

Beyond static categorization, longitudinal tracking is needed to capture the seasonality of student
sentiment. Santiago et al. (2025) emphasize the importance of identifying stress peaks that correlate with
the academic calendar, such as enrollment periods or midterms. BERTopic supports this through Dynamic
Topic Modeling (DTM), a feature described by Grootendorst (2022) that tracks how topic representations
evolve over time. Unlike standard LDA models, which are computationally rigid with respect to
time-series data, transformer-based models allow fluid visualization of trends, turning the Freedom Wall
from a chaotic feed into a structured timeline that supports proactive administrative foresight.

Traditional topic modeling methods, such as LDA, are inadequate for analyzing short, noisy, and
context-rich Freedom Wall posts. This limitation prevents accurate identification of semantically coherent
topics and the detection of temporal trends, creating a gap in understanding student discourse.
Transformer-based approaches, particularly BERTopic, are necessary to overcome these challenges and
enable reliable, context-aware topic analysis.

### 2.4 The Paradigm Shift in Sentiment Analysis......................................................................................

While topic modeling identifies the subjects of student discourse, sentiment analysis is needed to
measure the emotional intensity behind them. Traditionally, educational data mining has relied on binary
polarity, classifying feedback simply as positive or negative (Alkhnbashi & Nassr, 2023).
Rodriguez-Ibanez et al. (2023) argue that this approach loses critical nuance when applied to complex
social media data. A broad negative label conflates distinct emotional states, failing to differentiate
between the high-energy rage of a student protest and the low-energy hopelessness of academic burnout.
Santiago et al. (2025) emphasize that capturing these subtleties is essential for tracking stress peaks across
the academic calendar, which binary classifications cannot provide.

To address this limitation, this study adopts the Dimensional Theory of Emotion, mapping sentiment
along three continuous axes: Valence (Pleasure), Arousal (Intensity), and Dominance (Control). This
Hybrid VAD framework allows a precise assessment of campus climate. Panadero (2022) notes that the
Dominance dimension is especially important for evaluating student agency, distinguishing those who feel
victimized by the system (Low Dominance) from those who feel empowered to demand change (High
Dominance). By using this multidimensional approach, the university can move beyond simple
satisfaction metrics and identify specific behavioral risks, from passive withdrawal to active hostility.

Implementing this framework on code-switched text requires advanced capabilities. Kozlowski et al.
(2024) show that Large Language Models outperform traditional dictionary-based algorithms in


interpreting informal text context. This is particularly important for sarcasm detection. The AGH
University Team (2025) demonstrated that context-aware models can correctly identify ironic praise, such
as "Great job, admin" during a system failure, where standard tools fail. In addition, GenAI can support
data augmentation, generating synthetic examples of rare emotional states to balance the dataset (Prades,
2023). These technological advances ensure that the analysis captures the full spectrum of student
emotion accurately and in detail.

Traditional sentiment analysis methods, including binary polarity and dictionary-based algorithms, cannot
capture the nuanced, context-dependent emotions expressed in code-switched Freedom Wall posts. This
limitation hampers accurate monitoring of student welfare and may misrepresent the campus climate,
demonstrating the need for multidimensional emotion frameworks supported by context-aware AI
models.

### 2.5 Ethical Frameworks and Data Privacy............................................................................................

Collecting social media data requires navigating the tension between institutional utility and
student privacy. While Freedom Wall posts are publicly accessible, Gracia et al. (2025) emphasize that a
clear ethical line exists between public observation and unauthorized surveillance. To comply with legal
standards, this study follows the frameworks established by the National Privacy Commission and the
University of the Philippines Data Privacy Notice (2024). These guidelines confirm that processing
student data is lawful when it serves legitimate institutional interests, such as policy development and
campus welfare. Automated analysis of anonymous posts is therefore considered valid academic inquiry
into collective trends rather than targeted monitoring of individuals.

Operationalizing these mandates requires technical safeguards that go beyond simple confidentiality
assurances. The study adopts protocols for data minimization and anonymization recommended by the
Jotverse Editorial Team (2024). The scraping architecture collects only essential text and timestamps
while discarding user profiles and comment sections where identification risks are highest. Named Entity
Recognition is used to mask names of professors or students, and pseudonymization ensures that the
Freedom Wall’s safety valve function is preserved without exposing participants to doxxing or
reputational harm.

Finally, the limitations of the data source itself must be acknowledged. Alexander et al. (2019) note that
social media platforms often function as echo chambers, amplifying the voices of a vocal minority. As a
result, high-arousal emotions are overrepresented while silent or content students are underrepresented.
To address this bias, the findings are framed as an analysis of visible online discourse rather than a
comprehensive survey of the student population. This framing positions the Freedom Wall as a critical
early warning system for the segment of students most at risk.

Collecting and analyzing Freedom Wall data presents a dual challenge: ensuring student privacy while
generating actionable insights from a dataset that is inherently biased and partial. Addressing this problem
requires robust anonymization, ethical safeguards, and careful interpretation of results to understand
online student discourse without misrepresenting the broader student population.


### 2.6 Synthesis of the Reviewed Literature..............................................................................................

The reviewed literature shows a clear gap between how student discourse is understood in
sociology and how it is analyzed through technology. Three major areas of research exist, but they have
not yet been combined into a single framework.

First, sociological and educational studies such as Balabag and Potane (2024) and Montefalcon et al.
(2023) show that Freedom Walls function as safety valves for student expression and reveal the hidden
concerns of the university community. These studies rely on manual qualitative coding, which Soriano et
al. (2025) notes is no longer practical because of the growing volume of online posts. As a result,
universities understand the problem but lack scalable tools to monitor it.

Second, linguistic and technical research shows that common analytical tools are not suitable for the
Philippine context. Anacin (2022) and Manuel (2024) show that Taglish is a rule-governed system with
emotional depth. Yet, as Abisado et al. (2023) and Cabasag et al. (2025) point out, many NLP tools still
depend on English-based models or simple lexicons such as VADER. This creates a low-resource gap
where common Filipino expressions and cultural signals are not detected. Although Cruz and Cheng
(2021) introduced multilingual transformer models like RoBERTa-Tagalog, there is little applied work
using these advanced tools for informal, code-switched student discourse.

Third, the methodological literature shows major advances in algorithms that have not been fully adopted
in local research. Studies by ThirdEye Data (2025) and Egger et al. (2022) confirm that LDA performs
poorly on short, noisy social media texts. Meanwhile, Sy et al. (2024) and Khodeir (2025) show that
models like BERTopic deliver more coherent themes. Despite this, many local studies still rely on
outdated methods. In sentiment analysis, the common practice is still to classify text as positive or
negative, as described by Alkhnbashi and Nassr (2023). Rodriguez-Ibanez (2023) and Santiago et al.
(2025) argue that this is not enough for understanding student well-being. They highlight the need for the
Valence, Arousal, and Dominance framework, which is still missing in local studies.

These three areas reveal a clear research gap. No existing work combines multilingual transformers suited
for Taglish, BERTopic for short-text clustering, and a hybrid VAD approach for detailed emotional
analysis. Current studies are either sociological but lack computational depth, or computational but
misaligned with Philippine language use. This study addresses this gap by creating an end-to-end AI
pipeline designed for unstructured, code-switched, and emotionally complex student discourse. Its goal is
to convert Freedom Wall posts into reliable, ethical, and actionable institutional insights.

### 2.7 Framework.......................................................................................................................................

#### 2.7.1 Theoretical Framework..........................................................................................................

The study is anchored on several connected theories that explain how students communicate
online and why computational models must capture emotional intensity, contextual meaning, and
multilingual expression.

The Online Disinhibition Effect (Suler, 2004) explains why anonymity and reduced social cues in
Freedom Walls lead to stronger emotional expression. Students disclose vulnerability, frustration,


aggression, and distress more openly than in offline settings. Because emotions vary in intensity, the
dataset requires a sentiment model that measures degrees of affect, which supports the use of a
multidimensional VAD system instead of simple positive or negative labels.

The study also relies on the Distributional Hypothesis (Firth; Harris), which states that word
meaning depends on surrounding context. Traditional models like LDA treat words as independent and
fail to capture this structure, leading to weak topic quality. Transformer-based contextual embeddings
address this limitation by representing meaning through semantic proximity. This theoretical foundation
supports the use of BERTopic for clustering short, informal, and multilingual posts.

Emotional analysis is guided by Russell’s Circumplex Model, which locates emotions along
valence, arousal, and dominance. This framework captures both the type and intensity of emotion, as well
as the writer’s sense of control. Such nuance is essential for distinguishing passive distress from active
protest in student discourse, making VAD scoring more informative for campus monitoring.

From a sociolinguistic perspective, the study draws on Gumperz’s Functional Code-Switching,
which views language mixing as deliberate and meaningful. In Filipino digital spaces, Tagalog typically
signals closeness and emotional expression, while English signals formality. Taglish carries emotional and
social cues through its switching patterns, so it must be analyzed in its original mixed form rather than
translated. This supports the use of multilingual and code-switch–aware embeddings.

Together, these theories justify the study’s methodological choices: contextual embeddings,
BERTopic for topic modeling, VAD for emotion scoring, and multilingual text processing. They explain
why online student posts show strong emotional variation, why context is essential for meaning, why
emotions require multidimensional measurement, and why Taglish must be preserved during analysis.
These principles set the foundation for the Conceptual Framework, which organizes them within the
Input-Process-Output model.

#### 2.7.2 Conceptual Framework..........................................................................................................

This study uses the **Input-Process-Output (IPO)** model to show how unstructured Freedom Wall
posts are transformed into structured institutional insights. The input consists of text-only Taglish posts
from public Facebook Freedom Wall pages of UAAP and state universities, including timestamps and
engagement data from 2018 to 2025. Since the posts are short, informal, and noisy, they require
specialized preprocessing and short-text modeling.

The process has four stages.

1. **Preprocessing** removes noise such as URLs, HTML, and PII while preserving emotional cues in
    mixed-language text.
2. **Representation** converts cleaned text into contextual embeddings using fine-tuned
    RoBERTa-Tagalog.
3. **Analysis** applies BERTopic with HDBSCAN for topic extraction and uses a hybrid VAD model
    to score emotional intensity with support from large-language models.


4. **Validation** incorporates human-in-the-loop review, where annotators examine sample outputs in
    Label Studio to refine the model and ensure cultural accuracy.

```
Figure 1: Input-Process-Output Model
```
The outputs are three artifacts: a **topic model** tuned for Filipino student discourse, a Taglish V **AD
sentiment dataset** with both automated and human-verified labels, and a **dashboard** visualizing topic
clusters, emotional patterns, and cross-university trends. These outputs convert informal digital
expression into structured knowledge that supports data-driven decisions in higher education.


## 3. Design and Methods...............................................................................................................................

### 3.1 Research Design..............................................................................................................................

The research design in this study uses a Quantitative-Computational approach with Exploratory
Data Analysis. This method applies unsupervised machine learning to find hidden theme patterns in large
amounts of unstructured text. It differs from studies that test established theories. The design implements
an automated Natural Language Processing system to manage the heavy volume and complex language of
social media posts. By converting qualitative text into quantitative vectors and sentiment scores, the
research will depict the overall student experience beyond manual observation. The method for this study
is based on a pilot project conducted by the proponents (Albarida et al., 2025). Their test examined over
20,000 posts at the Saint Louis University Freedom Wall. It showed that transformer-based models
outperform the traditional probability approach for this type of data. The BERTopic system achieved a
coherence score of 0.58, which is better than the Latent Dirichlet Allocation (LDA) score of 0.34 for short
mixed-language text (see Appendix A, Figure 2). Because of this, our study adopted the proven
transformer-based setup to ensure accurate meanings. To improve external validity and analytical depth,
this research expands from a single institution to a multi-university dataset that includes major UAAP and
State Universities. Additionally, the design addresses limitations found in the pilot by enhancing the
sentiment analysis component. The basic classifier used earlier is replaced with a Hybrid
Valence-Arousal-Dominance (VAD) framework. This change allows for precise measurement of
emotional intensity and student involvement, offering a more detailed and useful assessment of
anonymous online feedback than simple polarity metrics could provide.

### 3.2 Data Collection................................................................................................................................

In this study, a thorough crawl of Freedom Wall posts from the Academic Years 2023-2024 and
2024-2025 will take place. This period was chosen to include multiple cycles of peak enrollment stress
and regular academic discussion. For universities with fewer than 10,000 posts during this time, the full
historical dataset will be used. For institutions with more posts than this, a stratified random sample will
keep the dataset at 10,000 posts per university.

This sampling limit is set to ensure computational efficiency within the hardware constraints of the local
inference environment (NVIDIA RTX 4050). It helps avoid processing delays while maintaining a large
enough sample size to achieve topic saturation. Data from the Pilot Study (SLU) will be used as a baseline
for the Baguio cluster to allow for longitudinal comparisons.

To ensure the quality of the dataset, the following inclusion and exclusion criteria will be applied:

```
● Posts must contain at least 50% Taglish content.
● Duplicate posts will be removed.
● Deleted or private posts will be excluded.
● Spam or bot-generated content will be filtered out.
```
All posts will be anonymized according to legal and ethical standards. The anonymization
pipeline includes:


1. Removal of usernames and user IDs using regular expressions.
2. Application of Named Entity Recognition (NER) to detect and mask names of students, faculty,
    or administrators.
3. Manual spot checks on a subset of 5% of posts to ensure effectiveness.

This study follows ethical guidelines set by the National Privacy Commission and the University
of the Philippines Data Privacy Notice (2024). Publicly accessible posts are used only for academic
analysis of overall trends, not for individual monitoring. A fallback protocol ensures that if any identifiers
are found after automated processing, the posts are either reprocessed or excluded.

Social media provides real-time feedback from students and other educational stakeholders. In the
Philippine context, Sy et al. (2024) showed that stakeholder sentiments on higher education policy,
particularly Universal Access to Quality Tertiary Education (UAQTE), can be accurately gathered and
analyzed using modern NLP tools. This study uses publicly accessible posts as a valuable, relevant source
for student discussions while upholding ethical standards.

### 3.3 Preprocessing...................................................................................................................................

Before applying topic modeling and sentiment analysis, the raw JSON data obtained from the
Freedom Wall scrapers must go through an extensive transformation process to turn unstructured noise
into a clean, meaningful corpus. The preprocessing pipeline is designed specifically to overcome the
challenges faced in the pilot study, where standard cleaning tools resulted in a high number of
unclassifiable data. The pipeline consists of five stages to ensure high-quality input for the multilingual
models.

#### 3.3.1 Field Selection and Structural Filtering.................................................................................

Field Selection and Structural Filtering The ingestion module authenticates the raw objects of the
Apify actor. The system enforces strict standards, storing only five basic fields: post unique identifier, text
content, engagements (likes, shares, comments), and date. Any unnecessary metadata, such as user profile
links in comments, media attachments, and site-specific tracking links, is immediately removed to comply
with data minimization protocols. Null values in the text are marked and excluded from the dataset to
avoid null-pointer errors during vectorization.

#### 3.3.2 Numeric and Engagement Normalization..............................................................................

Numeric and Engagement Normalization To ensure statistical consistency in downstream
analysis, all engagement fields are checked by converting non-numeric or missing values to zero. This
step standardizes interaction metrics, allowing the system to accurately link high-engagement posts with
specific high-arousal topics during analysis.

#### 3.3.3 Noise Reduction and Regex Cleaning...................................................................................

Noise Reduction and Regex Cleaning The textual content undergoes detailed cleaning with
predefined regular expressions. Common scraping artifacts such as "Submitted:" headers, indexing
hashtags, and footer signatures are removed to prevent these repetitive markers from creating artificial


clusters. Furthermore, the pipeline addresses specific "netspeak" trends in student discourse. A regex
substitution script identifies and normalizes character repetition (e.g., converting "haaaay" to "hay"),
which would otherwise create vector sparsity and confuse the embedding model.

#### 3.3.4 Linguistic Preservation and Tokenization..............................................................................

The pipeline does not include any machine translation steps. Manual (2024) states that intentional
bilingual thinking leads to mixed-language constructions. Phrases like “ _wala na talaga akong gana_ ”
express emotions that do not fit English equivalents. Translating them would remove critical
characteristics needed for proper sentiment analysis. Instead, the text is tokenized in its original form
using a multilingual-sensitive tokenizer trained to work with the RoBERTa-Tagalog architecture. This
helps maintain the structural and contextual meaning of mixed-language text while preserving its
emotional tone, as confirmed by Cosme and De Leon (2023).

#### 3.3.5 Context-Aware Stopword Removal.......................................................................................

To address the 44% outlier rate seen in the pilot study, the pipeline adds a special filtration step
for Tagalog pragmatic particles. Standard English stopword lists are not suitable for this dataset. The
researchers create a custom, context-aware Taglish stopword list that targets high-frequency particles like
po, naman, lang, pala, and kase. Manual (2024) points out that while these words indicate politeness or
flow, they do not convey the topic’s meaning needed for clustering. By filtering these terms, the algorithm
can concentrate on content-rich words like tuition, enrollment, or anxiety, significantly improving the
stability of the topic model.

#### 3.3.6 Academic Unit Categorization...............................................................................................

The cleaned posts are sorted into academic units using a **University-Specific Dictionary
Mapping** strategy. A configuration file containing the unique department acronyms for each of the 12
target universities (e.g., 'SAMCIS' for SLU, 'CSSP' for UP, 'GCOE' for DLSU) will be used. This method
is limited to explicit mentions of academic units or recognized department abbreviations. Posts with
informal references to academic units (e.g., "nursing," "engineering") may remain unclassified. The
system identifies the source university of each post and applies the relevant keyword dictionary to prevent
misclassification across institutions.

#### 3.3.7 Output Serialization...............................................................................................................

In the last stage, original ISO-format timestamps are converted to Unix epoch values and set to
the Asia/Manila timezone to support time-based analysis. The fully processed corpus is saved as a UTF-8
encoded JSON file called final_processed_text_posts.json. This file will be the standardized, high-quality
input for the downstream BERTopic and Hybrid VAD engines.

### 3.4 Topic Modeling................................................................................................................................

The researcher uses a topic modeling pipeline with BERTopic to extract themes from posts on Freedom
Wall. The process starts by generating semantic vectors using transformer-based embedding models. The
model used is the **paraphrase-multilingual-MiniLM-L12-v2** , chosen for its efficiency in managing


code-switching and informal language common in student texts. This model proved to be robust during
the pilot period, particularly when processing Taglish posts that mix English and Filipino syntax. The
RoBERTa-Tagalog model serves as a control group, allowing for more frequent handling of posts with
Filipino linguistic structures. This helps the system assess behavior based on language specifics and
stabilize embeddings. These embeddings capture semantic context better than just word frequency,
allowing for more accurate encoding of short, expressive social media posts.

After embedding, the **Uniform Manifold Approximation and Projection (UMAP)** technique reduces
the high-dimensional vectors without losing important neighborhood relationships. The dimensionality
reduction is set up to achieve a balance between local and global semantic structures, using 15 neighbors
and 5 components with cosine distance as the similarity metric. A mindist value of 0.05 helps maintain
tight and distinct clusters in the latent space. This reduced representation provides a solid base for
density-based clustering, bringing posts with similar meanings closer together.

Clustering is handled by the **HDBSCAN** density-based algorithm, which identifies clusters of varying
densities without needing to specify the number of topics. The study uses the optimization framework
from Farea et al. (2024), which involves an iterative grid search to adjust clustering settings and prevent
arbitrary selection of the number of topics. The model runs a mincluster range of 30-100, calculating
performance metrics like the Silhouette Score for cluster separation, NPMI Coherence for interpreting
topic descriptors, and an overall stability score to assess topic consistency across runs. This results in a
clustering structure that achieves the highest stability and coherence value. The process is mathematical,
meaning topic generation is based on empirical scores rather than analyst interpretation.

The system employs class-based **TF-IDF (c-TF-IDF)** to create interpretable topic descriptors by
identifying key terms in each cluster. It contrasts the aggregated documents of a cluster with the global
corpus. Since Freedom Wall posts often include conversational fillers and Taglish discourse markers, the
system has a custom Taglish stopword list developed in Section C. This list removes high-frequency,
meaningless words like po, naman, and lang, ensuring the extracted keywords convey significant thematic
information rather than stylistic noise. The result is a set of topic labels that accurately reflect student
issues and feelings.

To tackle the high number of outlier assignments (marked as Topic -1 in HDBSCAN) noted in the pilot
study, a **soft-clustering reassignment module** is added to the post-clustering phase. HDBSCAN
generates probability vectors for each document, showing the likelihood of belonging to neighboring
clusters. Posts initially labeled as outliers are re-evaluated, and any document with a membership
probability above a conservative 0.50 is reassigned to its most likely cluster. Posts below this confidence
threshold are kept as true noise and removed from the final topic distribution. This strategy significantly
enhances cluster completeness while maintaining the semantic coherence of core topics.

To keep local semantic context intact (for example, recognizing specific locations like 'Burnham' for
Baguio schools versus 'Katipunan' for QC schools), the BERTopic model is created separately for **each
university** dataset instead of combining all posts into a single global corpus. Thus, cross-university
comparisons occur at the interpretive level (comparing generated topic labels) instead of at the vector


level. This method ensures that distinct campus cultures are accurately represented without being
overshadowed by the overall data.

This BERTopic application, which focuses on engineering, offers a metrics-based workflow that addresses
the linguistic complexity of Taglish content. It reduces subjective decision-making and improves the
interpretability and reliability of the latent themes identified in Freedom Wall posts.

### 3.5 Topic Labeling and Hallucination Control......................................................................................

#### 3.5.1 Integration Architecture.........................................................................................................

The topic labeling component is integrated directly into the BERTopic workflow through the
bertopic.representation.TextGeneration module, enabling topic names to be generated immediately after
clusters are formed. This architecture embeds the language model inside the clustering pipeline rather
than treating labeling as a post-processing task, ensuring consistent synchronization between topic
formation and interpretation. All inference operations are executed locally on an NVIDIA RTX 4050
GPU, which provides sufficient computational capacity for low-latency processing while guaranteeing
full data privacy through on-device execution. The study employs a 4-bit quantized Llama-3-8B-Instruct
model, loaded through llama-cpp-python or Ollama, chosen for its strong reasoning capabilities in
multilingual and Taglish environments and its compatibility with local hardware resources. This
integration framework establishes a stable, secure, and efficient pathway for converting numerical clusters
into textual labels.

#### 3.5.2 Input Selection Strategy.........................................................................................................

To ensure that generated labels faithfully represent the underlying themes of each cluster, the
system adopts a selective input strategy that exposes the language model only to the most central elements
of the topic. Instead of analyzing the full corpus, the model receives two forms of distilled information per
cluster: the Top 10 c-TF-IDF keywords, which reflect the most distinctive vocabulary associated with the
topic, and the Top 5 representative documents, which are the posts closest to the cluster centroid in the
embedding space. This combination ensures that the model interprets both the abstract statistical signature
of the topic and the actual semantic content that defines it. By anchoring the labeling process to
centroid-based posts, the system guarantees that the language model reads authentic messages rather than
inferring themes solely from keyword lists, thereby strengthening contextual grounding and reducing
noise.

#### 3.5.3 Prompt Engineering...............................................................................................................

The labeling process is governed by a carefully engineered Role-Based Constraint prompt that
enforces uniform, reproducible outputs. Unlike Chain-of-Thought prompting, which generates verbose
reasoning, this approach applies strict negative constraints to ensure the output is immediately parseable
by the visualization engine. The system applies a structured persona encoded directly within the
TextGeneration module. The exact prompt used in the study is as follows:

```
You are an expert Data Analyst for a Philippine University. You analyze Taglish (Tagalog-English)
social media posts. Analyze the following keywords: [KEYWORDS] and representative posts:
```

_[DOCUMENTS]. Generate a label that is specific, short (maximum of five words), and professional. If
the posts are incoherent or spam, label the topic as ‘Noise’. Do not explain your reasoning; output only
the label._
This prompt establishes domain expertise, supplies the necessary linguistic context, and strictly
limits the response format. By prohibiting explanatory text, the system ensures that topic labels remain
focused and computationally cleaner, reducing the need for extensive post-processing regex cleaning.

#### 3.5.4 Hallucination Mitigation Protocols........................................................................................

To prevent the language model from generating inaccurate, invented, or overly broad topic labels,
the study implements a multilayer hallucination mitigation framework. The first safeguard involves
parameter locking, where the model’s Temperature is fixed at 0.1 to produce deterministic outputs and
suppress creative variation. After labeling, a post-processing script evaluates the generated text to detect
insufficiently specific or generic categories commonly referred to as “lazy labels.” Examples include
vague outputs such as “Student Life,” “General Concerns,” or other labels that do not directly reflect the
representative posts. Any such topic is flagged for re-generation or escalated for manual inspection.The
last line of defense is a Human Verification, which is explained in Section G, that involves trained
annotators comparing the labels created by an AI with the original representative posts. This
human-in-the-loop validation prevents all final topic names from being unreflective of the semantic limits
of their cluster and no hallucinated or misaligned labels ever finding their way into the final dataset. By
such a mixture of deterministic generation, filtering by algorithms and human supervision, the system
ensures good fidelity between algorithmically found topics and the textual descriptions of these topics.

### 3.6 Sentiment Analysis..........................................................................................................................

#### 3.6.1 The Hybrid Inference Architecture........................................................................................

The sentiment analysis component of the system is implemented through a hybrid inference
framework that combines unsupervised topic clustering with supervised generative scoring. This
architecture integrates the outputs of the BERTopic topic model with a large language model–based
sentiment engine to generate Valence–Arousal–Dominance (VAD) scores for each post. All inference
procedures are executed locally on an NVIDIA RTX 4050 GPU, ensuring low-latency processing and
maintaining full data privacy by avoiding external API dependencies. The system employs
Llama-3-8B-Instruct, quantized to either 4-bit or 8-bit formats to optimize memory usage while
preserving semantic reasoning capability. Each post is evaluated in combination with the topic label
assigned in Section E, allowing the model to interpret sentiment within the appropriate semantic context.
This contextual pairing prevents misinterpretation of polysemous terms; for example, when the assigned
topic concerns tuition or financial burdens, the word “mahal” is correctly understood as “expensive”
rather than “love.” Through this hybrid integration, the sentiment engine generates VAD outputs that are
sensitive to both linguistic and thematic cues embedded in the dataset.

#### 3.6.2 Prompt Engineering for VAD Quantification........................................................................

For the purpose of providing uniform and clear sentiment scores, the whole process relies on a
structured prompt design that through formalization applies the scoring rubric uniformly in the three VAD


dimensions. The model’s task is to rate every post according to the Self-Assessment Manikin (SAM)
method, which depicts feelings as continuous on a 1–9 scale. The scoring has Valence as the first
dimension, which on a scale of 1 to 9, where 1 indicates the presence of unpleasant or negative affect and
9 indicates the presence of pleasant or positive emotional tone. Arousal is the second dimension, which
has 1 at the low-end signifying calmness or low activation and 9 at the high-end signifying very high
excitement, agitation, or anger. Dominance is the third dimension, which on a scale of 1 to 9, where 1
indicates the situation is completely out of control or the person feels helpless and 9 indicates the
opposite, total control or empowerment. A strict JSON schema, for instance, {"V": 2, "A": 8, "D": 3}, is
applied to the model’s output so that it remains compatible with the computational pipeline and automated
dashboard. By mandating the SAM scale to come in the prompt and requiring a rigid output format, the
whole system creates quantifiable as well as machine-readable scores that correspond to psychometric
standards that are already established.

#### 3.6.3 Sarcasm Detection Protocol...................................................................................................

The methodology includes specialized mechanisms to address weaknesses observed during the
pilot study, particularly the model’s tendency to classify sarcastic or ironic expressions as “Unknown” or
“Incoherent.” This issue was especially evident in the SONAHBS dataset, where posts such as “Galing ng
admin!” were misclassified due to a lack of context. To correct this, the study adopts a Chain-of-Thought
(CoT) Prompting Strategy. Before generating the final VAD values, the model is instructed to generate an
intermediate reasoning step that evaluates linguistic markers associated with irony, sarcasm, “Conyo,” or
contradictory emoji–text combinations. This intermediate reasoning is discarded from the final JSON
output but serves to guide the model’s internal state towards a correct interpretation of nonliteral
emotional tones. This protocol substantially reduces “Unknown” labels and improves sentiment detection
accuracy for high-context Taglish communication.

#### 3.6.4 Data Balancing and Augmentation........................................................................................

To address the inherent class imbalance of social media datasets where high-arousal complaints
often dominate the corpus while low-arousal expressions (e.g., depression, burnout) are underrepresented,
the study adopts an In-Context Learning (ICL) strategy. Prades (2023) highlights that models often
struggle to detect rare emotional states when the inference examples are heavily skewed. To mitigate this,
the system employs Few-Shot Prompting, where the input prompt is augmented with specific,
linguistically verified examples of rare Taglish sentiment expressions. This technique effectively
"anchors" the model's understanding of subtle linguistic patterns associated with passive or low-valence
emotions. By providing these curated examples within the inference window, the methodology ensures
robust detection across the entire emotional spectrum without the computational overhead of fine-tuning
model weights.

### 3.7 Validation Strategy (Human-in-the-Loop).......................................................................................

The paper will employ a Human-in-the-Loop (HITL) strategy to validate the credibility of the
outputs of both the topic modeling and the VAD sentiment analysis. The concept of this strategy is rooted
in the fact that, as mentioned in the human centred AI literature, AI models used in socially significant


contexts should be controllable by humans rather than be considered as entirely autonomous and fallible.
Since most posts on Freedom Wall contain culturally specific words and expressions, humor, indirectness
and emotional sensitive content, human discretion is needed to prevent misclassification and model
hallucination. Studies of machine learning systems also warn of unknown risks on the system level, which
can make the unverifiable outputs costly to rely on.

The validation process will be completed with the help of the Label Studio, which is an
open-source annotation system, which will support categorical labeling, continuous scoring, and
agreement between annotators. The sample of the study will be a stratified random sample of
approximately 5 percent of the number of posts in every university which has passed the first AI
processing and is human reviewed. The stratification will be based on campus, academic term and
distribution of AI produced topics in a way that one will be able to locate the common as well as the
unusual patterns of the language. This enables the prevention of evaluation bias, and follows the
recommendation to avoid hidden technical debt and other machine learning validation pitfalls.

Eight (8) qualified human beings will be validating when they will have the approval of this
proposal. They will receive systematic training to ensure that they are constant in the use of topic labels
and VAD scores. Training will also involve a calibration workshop which will involve instructions on
annotation, posting of samples, emotion rating anchors and processed ambiguous or potentially unhealthy
content. Pilot annotation rounds (100-200 posts) will be offered to receive an idea of whether the
guidelines have a shared understanding among the validators before the actual validation is conducted.

Inter-Rater Reliability (IRR) will be employed to assess the consistency of the AI system against
human judgment. The study utilizes Cohen’s Kappa to test the inter-rater agreement of categorical topic
labels and the Intraclass Correlation Coefficient (ICC) for continuous VAD emotional scores. Following
the interpretation guidelines established by Landis and Koch (1977), a coefficient of κ > 0.61 will be
considered 'Substantial Agreement,' with a target threshold of κ ≥ 0.70 to denote satisfactory model
performance. These thresholds are congruent with standard acceptance criteria in computational social
science and linguistic annotation tasks. The emphasis on rigorous IRR ensures that the resulting dataset is
not merely an output of algorithmic conjecture but a validated artifact of human-machine consensus.

Should the agreement between the human validators and the AI be low in the event that it falls
below acceptable levels, then the model is liable to be refined. This may be through parameter
optimization of BERTopic or rewriting topic label prompts, inclusion of more representative examples or
inclusion of more domain specific linguistic data to the corpus. A new stratified sample will be checked
with a new stratified sample to explain whether improvements are made. Such a cycle is aligned with the
principle of responsible AI development and is a reminder of the fact that human correction is an
important element of trustful deployment. External debates of HITL and interactive feedback of ML
support this philosophy.

The strategy of HITL validation is one of the approaches the study uses to make sure that the
utilization of AI does not result in the adoption of unfiltered output, that cultural and emotional
complexities are adequately comprehended, and that the final dataset relates to the evidence of
congruence between human and machine analysis. The process does not only produce believable output,


but also human approved high quality subset of data, which can be further benchmarked, reproduced and
refined.

### 3.8 Tool Development and System Architecture...................................................................................

In order to make the concept of the AI models ready to be applied to the real world, and to
overcome the institutional latency outlined in the Introduction, the paper is accompanied by the creation
of a fully functioning web-based dashboard. The tool is the key entrance point between the computational
back-end and the university administrators since it converts raw data in the form of vector space into
visualizations that are easy to interpret and take action. The architecture of the system is a local and
on-premise application that should be able to execute on high-performance workstations able to utilize the
RTX 4050 inference engine. Such local deployment strategy will make sure that sensitive information is
not transferred to the unsafe online infrastructure of the research facility but rather makes use of the
required GPU acceleration to conduct real-time model inference.

The system is built on the Flask framework, a lightweight Python-based web server selected for
its ease of integration with backend data science libraries. In contrast to traditional reporting systems,
Flask allows data to be dynamically rendered based on the processing pipeline and does not have to store
intermediate data in a warehouse. The frontend visualization layer is based on Chart.js, which is a
JavaScript library that is optimized to draw responsive and interactive graphs. The option enables the
system to create finer visualizations to track sentiment trends and topic frequency in the form of
time-series line graphs and dynamic bar charts respectively without the latency of heavy business
intelligence platforms. It is containerized in such a manner that makes it reproducible across local
environments eliminating dependency conflicts between the web server and the accelerated libraries of
modelling using the GPUs.

The system uses a Scheduled Batch Pipeline instead of a stream connection in order to offer the
monitoring capabilities without exploiting the rate limits of social media platforms. The data ingestion
module is activated with a cron-type scheduler with 24 hour periods. In this cycle, the system will run the
scraping script to fetch the new posts only those which were created the day before. The Preprocessing
Pipeline of Section C passes these new entries that are in turn inferred by the BERTopic and Hybrid VAD
models that are already trained. The outputs are attached to the primary data that enables the dashboard to
indicate the prevailing condition of student sentiment with a latency of 24 hours maximum. This
architecture provides a necessary tradeoff between the desire to have early warning signals as soon as
possible and technical capability of scraping stability.

Due to the characteristics of the tool, which are prototypical, and the size of the dataset that is not
overwhelming, the system is based on a flat-file system of data storage in the form of JSON instead of a
heavyweight relational database. The effect of this decision is that the overhead latency of SQL queries is
minimized and the process of deployment becomes easy. The processed data is the one that is serialized as
hierarchical JSON files that are read-heavy. These files are automatically read into Pandas DataFrames in
memory when starting up and can be filtered and cross-referenced on their contents almost instantly as the
user interacts with it.


The user interface will provide answers to the particular operational questions of the university
administrators in three separate visualization modules. The Global Overview Module displays a top-down
heatmap of the university emotional state with the help of VAD scores, to designate high-arousal days.
The Topic Drill-Down Module enables the user to be able to browse particular collections of topics, and
see the representative posts related to that particular topic. Lastly, the Temporal Analysis Module is used
to visualise the trend of sentiment throughout the semester. This enables the administrators to associate
spikes in negative sentiment with certain dates in the academic year including the week of enrollment or
final exams.

### 3.9 Ethical Considerations and Limitations...........................................................................................

This research project will follow a very stringent code of ethics and security measures that aim at
safeguarding the privacy, dignity, and safety of the students who appear on the public Freedom Wall sites
in their posts. The following procedures form the binding compliance framework of the project in
connection to the data minimization, anonymization, secure storage, and harm-mitigation. These
protections will keep any research project within the limits of law, preserving privacy, and in accordance
with the ethical codes of the institution.

#### 3.9.1 Data Minimization Protocol...................................................................................................

To prevent the unnecessary collection of personal or sensitive information, the scraper is
configured with enforced constraints at the code level. The Apify Facebook Page Scraper is whitelisted
and retrieves only the content of the post, the time, and the number of reactions. All the other fields are
automatically deleted, such as user profile URLs, usernames, embedded media, and the comments section
which contains tagging since it is a common practice. No uncooked HTML, metadata or personally
identifying information that is not part of the approved fields is stored. This will ensure that the data that
is sent to the research only holds data that is critical to the topic modeling and sentiment analysis process,
thus minimising the amount of exposure to privacy at the moment of data collection.

#### 3.9.2 Anonymization Pipeline.........................................................................................................

All raw text is subjected to an extensive anonymization process before it is subjected to any
computational processing. The first step in the dataset is a Named Entity Recognition (NER) pipeline
running on spaCy or Microsoft Presidio. Entities marked as PERSON are automatically substituted with
the generic token [REDACTED_NAME] so that it is impossible to tell about the identity of an individual
through proper nouns. Meanwhile, regular expression filters are used to take out student numbers, phone
numbers, email addresses, and other structured identifiers. Where posts have references that might
indirectly identify people (e.g. a particular professor or a department) these are replaced with placeholders
(e.g. [PROFESSOR_NAME]) or placeholders (e.g. [DEPARTMENT]). None of the textual data is then
subjected to topic modeling, VAD scoring or human validation before it has been subjected to these
exhaustive anonymization measures.


#### 3.9.3 Data Storage and Security Protocol.......................................................................................

Raw and intermediate data are stored only on local and encrypted drives BitLocker or VeraCrypt.
The storage system is stored in a non-networked workstation with a RTX 4050 GPU, which also means
that the machine is not accessible via the internet, Wi-Fi, or cloud-synchronized systems. The access to
this workstation is limited to the main researcher and must be performed physically as well as with the
help of encryption keys. Raw JSON content, scrapes, and unmasked text are never uploaded to cloud
services. Documentation or panel assessment The only data that may be stored in Google Drive is fully
anonymized, aggregated results, including clusters of topics, sentiment distributions, or risk heatmaps.
Once the research is completed, raw datasets will be overwritten with secure multi-pass overwrite
measures in order to ensure that no data can be recovered.

#### 3.9.4 “Do No Harm” Trigger Protocol............................................................................................

Because the expression of students on Freedom Walls is a sensitive matter, this study introduces a
harm-reduction system, which will deal with the posts that signal the presence of a psychological threat.
The sentiment analysis engine is set to mark the entries with high arousal and negative valence, especially
when the entry includes words signaling self-harm (e.g., such words as end it all). As the dataset is
retrospective and anonymized, the research team cannot and will not be able to interfere with individual
students. Rather, flagged postings are part of creating aggregate levels of Risk Heatmaps, which
summarize the frequency and thematic concentration of crisis-related rhetoric. These anonymized
heatmaps are sent to the University Guidance Office to aid in the creation of mental health programs,
early-warning mechanisms and student-support policies. In the process, the research team is highly
forbidden to make efforts of tracing, identifying, and reaching out to the authors of any posts.

It is important to note that this study utilizes retrospective data collected via batch processing, not
real-time monitoring. Furthermore, the inherent 'double-blind' anonymity of Freedom Wall platforms
makes the identification of specific authors technically impossible for the researchers. Consequently, the
'Do No Harm' protocol focuses on Systemic Risk Reporting rather than individual intervention.

Instead of attempting to trace specific students—which would violate privacy and is operationally
unfeasible—the system utilizes high-risk markers to generate aggregate Crisis Heatmaps. These heatmaps
provide University Guidance Offices with actionable intelligence on when (e.g., specific weeks) and
where (e.g., specific departments) distress levels peak, enabling institutions to deploy proactive mental
health programs and systemic support interventions during critical periods."

### 3.10 Summary of Methodology.............................................................................................................

```
Step Phase Type Description
```
```
1 Research Design Quantitative–Computational Utilizes an exploratory data analysis
approach with unsupervised machine
```

```
learning to analyze large-scale,
unstructured Freedom Wall text data.
```
2 **Data Collection** Data Acquisition Collects publicly available Facebook
Freedom Wall posts from selected UAAP
and State Universities using the Apify
Facebook Page Scraper with stratified
sampling.

3 **Preprocessing** Data Preparation Applies schema filtering, numeric
normalization, regex-based noise
reduction, Taglish-preserving
tokenization, context-aware stopword
removal, and data serialization.

4 **Topic Modeling** Unsupervised Learning Implements BERTopic with
transformer-based embeddings, UMAP
dimensionality reduction, and
HDBSCAN clustering to extract latent
themes from short-text posts.

5 **Topic Labeling** Generative AI Generates concise and context-aware
topic labels using a locally deployed
large language model with controlled
prompting and hallucination mitigation.

6 **Sentiment Analysis** Hybrid AI Inference Applies a Valence–Arousal–Dominance
(VAD) framework using generative AI to
quantify emotional intensity and student
agency in each post.

7 **Validation Strategy** Human-in-the-Loop Conducts human validation using Label
Studio on a stratified sample of posts and
evaluates reliability through Cohen’s
Kappa and Intraclass Correlation
Coefficient.

8 **System Architecture** Tool Development Develops a local, GPU-accelerated
Flask-based dashboard to visualize topic
distributions, sentiment trends, and
temporal patterns.

9 **Ethical Safeguards** Data Governance Enforces data minimization,
anonymization, secure storage, and


ethical AI protocols in compliance with
Philippine data privacy regulations.


**References**

Abisado, M. B., et al. (2023). Sentiment analysis of code-mixed social media data on Philippine UAQTE
using fine-tuned mBERT model. International Journal of Advanced Computer Science and
Applications.

Albarida, I., Calera, E. D., De Leon, T., Gapuz, E. J., Modelo, A. E., Marcos, J. P., Moreno, J. L., &
Salda, J. (2025). Developing an AI-driven tool for topic modeling and sentiment analysis of
student discourse on SLU's Freedom Wall. [Unpublished Pilot Study]. Saint Louis University.

Alexander, B., Ashford-Rowe, K., Barajas-Murphy, N., et al. (2019). EDUCAUSE Horizon Report: 2019
higher education edition. EDUCAUSE.
https://library.educause.edu/-/media/files/library/2019/4/2019horizonreport

Alexander, D., Wilkens, J., Nunn, A., & Martin, C. (2019). Algorithmic bias in educational data systems.
Journal of Learning Analytics, 6(3), 44–57.

Alkhnbashi, O. S., & Nassr, R. M. (2023). Topic modelling and sentimental analysis of students’ reviews.
Computers, Materials & Continua, 74(3), 6835–6848. https://doi.org/10.32604/cmc.2023.034987

Amershi, S., Cakmak, M., Knox, W. B., & Kulesza, T. (2014). Power to the people: The role of humans in
interactive machine learning. AI Magazine, 35(4), 105–120.

Karizza P. Bravo-Sotelo, (2022). Exploring the Tagalog-English Code-Switching Types Used for
Mathematics Classroom Instruction. IAFOR Journal of Education.

Andrei D. Espina, Joan S. Jose, Joffrey Luna, James Maico M. Velasco, Ronald Fernandez (2025). Smart
Faculty Evaluation: A Mobile App Using NLP-Based Sentiment Analysis and Random Forest for
Faculty Assessment at Universidad De Manila. International Journal of Research and Innovation
in Social Science (IJRISS), 9(09), 5365-5381.
https://dx.doi.org/10.47772/IJRISS.2025.909000434

Balabag, M. D. & Potane, J. D. (2024). Describing the Use of Freedom Wall in Expressing Students’
Emotion. Journal of Interdisciplinary Perspectives, 2(7), 375-384.
https://doi.org/10.69569/jip.2024.0112

Blei, D. M., Ng, A. Y., & Jordan, M. I. (2003). Latent Dirichlet allocation. Journal of Machine Learning
Research, 993–1022.

Cohen, J. (1960). A coefficient of agreement for nominal scales. Educational and Psychological
Measurement, 20(1), 37–46.


Cosme, Camilla & Leon, Marlene. (2024). Sentiment Analysis of Code-Switched Filipino-English
Product and Service Reviews Using Transformers-Based Large Language Models.
10.1007/978-981-99-8349-0_11.

Cruz, J. C. B., & Cheng, C. (2021). Establishing a baseline for Philippine local language models.
arXiv:2110.11583.

Dalipi, F., et al. (2021). Sentiment analysis of students' feedback in MOOCs. Frontiers in Artificial
Intelligence, 4, 674681, Volume 4.

Egger, R., et al. (2022). A topic modeling comparison between LDA, NMF, and BERTopic. Frontiers in
Sociology, 7, 919299, Volume 2.

Ellwood-Clayton, B. (2005). All we need is love—and a mobile phone: Texting in the Philippines. In R.
Harper, A. Palen, & A. Taylor (Eds.), The inside text: Social, cultural and design perspectives on
SMS (pp. 195–219). Springer.

Farea, A., Tripathi, S., Glazko, G., & Emmert-Streib, F. (2024). Investigating the optimal number of
topics by advanced text-mining techniques: Sustainable energy research. Engineering
Applications of Artificial Intelligence, 136, 108877.
https://doi.org/10.1016/j.engappai.2024.108877

George L, Sumathy P. An integrated clustering and BERT framework for improved topic modeling. Int J
Inf Technol. 2023;15(4):2187-2195. doi: 10.1007/s41870-023-01268-w. Epub 2023 May 6.
PMID: 37256029; PMCID: PMC10163298.

Gracia, M., Santos, R., & Yu, P. (2025). Public observation vs. surveillance in digital research. Philippine
Journal of Digital Studies, 2(1), 14–29.

Grootendorst, M. (2022). BERTopic: Neural topic modeling with a class-based TF-IDF procedure.
arXiv:2203.05794.

Hayat, Faiz & Shatnawi, Safwan & Haig, Ella. (2024). Comparative Analysis of Topic Modelling
Approaches on Student Feedback. 226-233. 10.5220/0012890400003838.

ISO/IEC. (2013). ISO/IEC 27001: Information security management systems. International Organization
for Standardization.

Jordan D.C. Manuel (2024). Unpacking the Bilingual Mind: How Code Mixing and Switching Facilitate
Language Processing among Bilingual Learners. International Journal of Research and Innovation
in Social Science (IJRISS), 8(06), 2754-2772. https://dx.doi.org/10.47772/IJRISS.2024.806210


Jotverse Editorial Team. (2024). 6 Student data anonymization techniques.
Jotverse.https://www.jotverse.com/6-student-data-anonymization-techniques/

Ishmael, Ontiretse & Kiely, Etain & Quigley, Cormac & McGinty, Donal. (2023). Topic Modelling using
Latent Dirichlet Allocation (LDA) and Analysis of Students Sentiments. 1-6.
10.1109/JCSSE58229.2023.10201965.

Khodeir, N., & Elghannam, F. (2024). Efficient topic identification for urgent MOOC forum posts using
BERTopic and traditional topic modeling techniques. Education and Information Technologies,
30(5), 5501–5527. https://doi.org/10.1007/s10639-024-13003-4

Koráb, P. (2025). Topic model labelling with LLMs. Towards Data Science.
https://towardsdatascience.com/topic-model-labelling-with-llms/

Kozlowski, D., et al. (2024). Generative AI for automatic topic labelling. arXiv:2408.07003.

Krippendorff, K. (2013). Content analysis: An introduction to its methodology (3rd ed.). SAGE
Publications.

Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for categorical data.
Biometrics, 33(1), 159–174. https://doi.org/10.2307/2529310

Lyon, D. (2018). The culture of surveillance: Watching as a way of life. Polity Press.

Marie-Francine Moens, Xuanjing Huang, Lucia Specia, and Scott Wen-tau Yih. 2021. Proceedings of the
2021 Conference on Empirical Methods in Natural Language Processing. Association for
Computational Linguistics, Online and Punta Cana, Dominican Republic.

McGraw, K. O., & Wong, S. P. (1996). Forming inferences about some intraclass correlation coefficients.
Psychological Methods, 1(1), 30–46.

Montefalcon, M. D. L., Padilla, R. B., Perez, J. S., & Santos, A. S. (2023). The post behind anonymity: A
thematic discourse analysis of Facebook posts from confession pages in different universities in
the Philippines. ResearchGate.

National Privacy Commission. (2020). Data Privacy Council Education Sector Advisory No. 2020-1:
Data privacy and online
learning.https://privacy.gov.ph/wp-content/uploads/2023/05/DP-Council-Education-Sector-Advis
ory-No.-2020-1.pdf


Ortiz, M. G., & Dumlao, M. (2025). AI-Driven Insights from Student Feedback for Teacher
Improvement. Journal of Interdisciplinary Perspectives, 3(8), 503–513.
https://doi.org/10.69569/jip.2025.418

Panadero, Ernesto & Lipnevich, Anastasiya. (2021). A review of feedback typologies and models:
Towards an integrative model of feedback elements. Educational Research Review. 35. 100416.
10.1016/j.edurev.2021.100416.

Pangilinan, A. C., et al. (2021). Anonymous whispers: A critical discourse analysis on digital gossip in
select Philippine university Freedom Walls. In Proceedings of the DLSU Research Congress

2021. De La Salle University.
https://animorepository.dlsu.edu.ph/conf_shsrescon/2025/paper_mps/11/

Pertierra, R. (2005). Mobile phones, identity, and discursive intimacy in the Philippines. Human
Technology: An Interdisciplinary Journal on Humans in ICT Environments, 1(1), 23–44.

Prades, G. S. (2023). Modelling sentiment analysis: LLMs and augmentation techniques.
arXiv:2311.04139.

Rodriguez, Ramon & Padilla, Jay & Montefalcon, Myron Darrel & Abisado, Mideth & Raga, Rodolfo.
(2023). The Post Behind Anonymity: A Thematic Discourse Analysis of Facebook Posts from
Confession Pages in different Universities in the Philippines. 529-533.
10.1109/ICIET56899.2023.10111104.

Rodríguez-Ibánez, M., et al. (2023). A review on sentiment analysis from social media platforms. Expert
Systems with Applications, 235, 121017.

Santiago, C. S., et al. (2025). Sentiment analysis of students' experiences during online learning in a state
university. ResearchGate.

Soriano, M. A., Maddalora, A. L. M., & Vinluan, A. A. (2025). Enhancing online learning through
feedback analytics using descriptive analytics and topic modeling. Journal of Innovative
Technology Convergence, 7(2).DOI: https://doi.org/10.69478/JITC2025v7n2a05

Sy, C. Y., et al. (2024). Leveraging transformer-based BERTopic model on stakeholder insights towards
Philippine UAQTE. Frontiers in Education, 9, 1234567.
https://ijettjournal.org/Volume-72/Issue-3/IJETT-V72I3P125.pdf

Tabloid Editorial Board. (2025). Lycean Freedom Wall (FWall) triggers discourse. LPU Batangas.
https://lpubatangas.edu.ph/wp-content/uploads/2025/08/TABLOID_compressed.pdf


ThirdEye Data Team. (2025). Topic modelling using LDA (updated for 2025).
https://thirdeyedata.ai/machine-learning/topic-modelling-using-lda-updated-for-2025/

University of the Philippines. (2024). UP Data Privacy Notice for students.
https://privacy.up.edu.ph/privacy-notices/privacy-notice-for-students-1st-sem-2024-2025-1.1.pdf

Uy-Tioco, C. S. (2004). Texting capital: Mobile phones, social transformation, and the reproduction of
power in the Philippines (Doctoral dissertation). University of Toronto. ProQuest Dissertations & Theses
Global.

We Are Social, & Hootsuite. (2019). Digital 2019: Global digital overview.
https://www.slideshare.net/DataReportal/digital-2019-global-digital-overview


**Annexes**

**NOTE TO THE PANEL:**
This Annex contains the results of a preliminary pilot study conducted by the proponents. This pilot served as a
feasibility test for the current proposal.

Key Differences Between Pilot and Proposal:

1. **Scope** : The Pilot was limited to SLU only. The Proposal expands to UAAP & State Universities.
2. **Sentiment** : The Pilot used basic Llama-3 prompting, resulting in high "Unknown" rates. The Proposal uses
    a Hybrid VAD Chain-of-Thought framework.
3. **Validation** : The Pilot had limited validation. The Proposal utilizes Label Studio with strict Inter-Rater
    Reliability metrics.

**ANNEX A : Proof of Concept and Pilot Study Results**
_Preliminary Evaluation of BERTopic vs. LDA on the SLU Freedom Wall Dataset (July 2024–May 2025)_



