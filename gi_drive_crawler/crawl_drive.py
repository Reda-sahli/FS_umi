#!/usr/bin/env python3
"""
=============================================================================
Google Drive API v3 — Recursive Crawler for Génie Informatique Portal
=============================================================================
Crawls S3, S4, S5, S6 semester folders, extracts all file IDs,
classifies resources, and generates the final gi_database.json.

SETUP:
  1. pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
  2. Place credentials.json (OAuth 2.0 Desktop App) or service_account.json
     in the same directory as this script.
  3. python crawl_drive.py
=============================================================================
"""

import os
import re
import json
import time
from pathlib import Path
from datetime import datetime

# ── Google API imports ────────────────────────────────────────────────────────
try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.oauth2 import service_account
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
except ImportError:
    print("❌  Missing dependencies. Run:\n"
          "    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    raise SystemExit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# Scopes — read-only is sufficient
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Root semester folder IDs (confirmed from live Drive pages)
SEMESTER_FOLDERS = {
    "S3": "1Uydpe13HG_HekDJ436jj66D62wkoVlUo",
    "S4": "1up_Ht85GujXL2CH03dM1kUAWVAAw8CKi",
    "S5": "1ji08TCdWwlndE5KvB6VqircU26ZLwNim",
    "S6": "1lHZJ7BlH6rSpCI6tcpmrqGf-p7WjlTJN",
}

MAJOR = "Génie Informatique"
OUTPUT_FILE = Path(__file__).parent / "gi_database_final.json"
TOKEN_FILE  = Path(__file__).parent / "token.json"
CREDS_FILE  = Path(__file__).parent / "credentials.json"       # OAuth Desktop App
SA_FILE     = Path(__file__).parent / "service_account.json"   # Service Account (alt)

# ══════════════════════════════════════════════════════════════════════════════
#  TAXONOMY RULES
# ══════════════════════════════════════════════════════════════════════════════

# Academic year regex: matches "(2023-2024)" or "2023-2024"
YEAR_REGEX = re.compile(r"\(?(\d{4}[-–]\d{4})\)?")

# Category classification rules (ordered — first match wins)
CATEGORY_RULES = [
    ("EXAMEN", re.compile(r"exam|controle|contrôle|ds\b|devoir|rattrapage|partiel", re.IGNORECASE)),
    ("TP",     re.compile(r"\btp\b|travaux\s+pratiques|lab\b|pratique", re.IGNORECASE)),
    ("TD",     re.compile(r"\btd\b|travaux\s+dirig[eé]s|exercices?\b|s[eé]rie", re.IGNORECASE)),
    ("COUR",   re.compile(r"\bcours?\b|lecture|poly|support|chapitre|chap\b", re.IGNORECASE)),
]

# Known module name patterns → canonical module name
MODULE_PATTERNS = [
    (re.compile(r"algor|asd|structure.*donn|donn.*struct", re.IGNORECASE),
        "Algorithmique et Structures de Données (ASD)"),
    (re.compile(r"langage\s*c|prog.*i\b|prog.*1\b|programmation.*c\b", re.IGNORECASE),
        "Prog I (Langage C)"),
    (re.compile(r"syst[eè]me.*exploit|exploit.*syst[eè]me|\bse\b|\bos\b", re.IGNORECASE),
        "Systèmes d'Exploitation (SE)"),
    (re.compile(r"logique|graphe|math.*info|discr[eè]t", re.IGNORECASE),
        "Mathématiques pour l'Informatique (Logique & Graphes)"),
    (re.compile(r"architecture|archi\b|processeur|pipeline|assem", re.IGNORECASE),
        "Architecture des Ordinateurs"),
    (re.compile(r"base.*donn[eé]e|donn[eé]e.*base|\bbd\b|\bsgbd\b|sql|oracle|merise", re.IGNORECASE),
        "Bases de Données (BD)"),
    (re.compile(r"orient[eé].*objet|poo|java\b|prog.*ii|prog.*2", re.IGNORECASE),
        "Programmation Orientée Objet (POO — Java)"),
    (re.compile(r"r[eé]seau|network|cisco|tcp|ip\b|vlan|routage", re.IGNORECASE),
        "Réseaux Informatiques"),
    (re.compile(r"th[eé]orie.*lang|lang.*th[eé]orie|compil|automate|grammaire|tlc|tl\b", re.IGNORECASE),
        "Théorie des Langages et Compilation (TLC)"),
    (re.compile(r"num[eé]rique|analyse.*num|num.*analyse", re.IGNORECASE),
        "Analyse Numérique"),
    (re.compile(r"techno.*web|web.*techno|html|css\b|php\b|javascript|node", re.IGNORECASE),
        "Technologie Web (TechnoWeb)"),
    (re.compile(r"intellig.*artif|artif.*intellig|\bia\b|machine.learn|ml\b|deep.learn|neural", re.IGNORECASE),
        "Intelligence Artificielle (IA)"),
    (re.compile(r"g[eé]nie.*logiciel|logiciel.*g[eé]nie|\bgl\b|uml|design.pattern|agile|scrum", re.IGNORECASE),
        "Génie Logiciel (GL)"),
    (re.compile(r"proba|statistique|stochast|markov", re.IGNORECASE),
        "Probabilités et Statistiques pour l'Informatique"),
    (re.compile(r"s[eé]curit[eé]|crypto|rsa\b|aes\b|cipher|firewall|pentest", re.IGNORECASE),
        "Sécurité Informatique"),
    (re.compile(r"distribu[eé]|cloud|docker|kubernetes|microservice|nosql|hadoop|spark", re.IGNORECASE),
        "Systèmes Distribués et Cloud Computing"),
]

# E-E-A-T Module editorial metadata (pre-authored, AdSense compliant)
MODULES_METADATA = {
    "Algorithmique et Structures de Données (ASD)": {
        "semester_hint": "S3",
        "prerequisites": ["Programmation de base", "Mathématiques discrètes"],
        "description": "Ce module est l'un des piliers fondamentaux de la formation en Génie Informatique. Il couvre les algorithmes classiques de tri (bulles, insertion, fusion, rapide), la complexité temporelle (notation Big-O), et les structures de données linéaires et non-linéaires : tableaux, listes chaînées simples et doublement chaînées, piles (LIFO) et files (FIFO). Les étudiants apprennent à implémenter et analyser ces structures en langage C ou Java. Les arbres binaires, arbres de recherche binaire (BST), et les tables de hachage sont également abordés. Pour réussir les examens, il faut maîtriser l'implémentation des piles avec tableaux et pointeurs, et savoir calculer la complexité d'un algorithme récursif. Conseil aux étudiants marocains : exercez-vous quotidiennement sur des problèmes de LeetCode en arabe ou français pour solidifier vos bases avant la session.",
        "key_exam_topics": ["Implémentation des Piles et Files (tableaux vs pointeurs)", "Tris comparatifs : complexité et trace d'exécution", "Arbres Binaires de Recherche (BST) : insertion, suppression, parcours", "Listes chaînées : inversion, détection de cycle", "Calcul de complexité Big-O"]
    },
    "Prog I (Langage C)": {
        "semester_hint": "S3",
        "prerequisites": ["Initiation à l'informatique"],
        "description": "Le module Programmation I en Langage C constitue la première immersion profonde dans un langage système pour les étudiants de SMI3. On y apprend la syntaxe C, les types primitifs, les opérateurs, les structures de contrôle (if/else, for, while, do-while, switch), et les fonctions. La gestion de la mémoire dynamique via malloc(), calloc(), realloc() et free() est centrale : comprendre le tas (heap) et la pile (stack) est indispensable pour éviter les fuites mémoire. Les pointeurs, arithmétique des pointeurs, et les tableaux multidimensionnels sont traités en profondeur. La manipulation des fichiers texte et binaires (fopen, fread, fprintf) figure également au programme. Côté examen, les exercices portent souvent sur l'implémentation d'une liste chaînée, d'une pile ou d'un arbre binaire en C pur. Conseil : lisez systématiquement les erreurs de segmentation avec GDB pour développer vos réflexes de débogage.",
        "key_exam_topics": ["Pointeurs et allocation dynamique (malloc/free)", "Manipulation de fichiers texte et binaires", "Implémentation de listes chaînées en C", "Fonctions récursives et passage par référence", "Structures (struct) et unions"]
    },
    "Systèmes d'Exploitation (SE)": {
        "semester_hint": "S3",
        "prerequisites": ["Architecture des ordinateurs", "Algorithmique S2"],
        "description": "Ce module introduit les concepts fondamentaux des systèmes d'exploitation modernes. Les étudiants étudient la gestion des processus (création, ordonnancement FCFS, SJF, Round Robin, priorités), la synchronisation (sémaphores, moniteurs, problème producteur-consommateur), et la gestion de la mémoire (pagination, segmentation, mémoire virtuelle). Les concepts de deadlock (détection, prévention, évitement par algorithme du banquier) sont traités en détail. La gestion des fichiers (systèmes de fichiers FAT, ext4, inodes) et la communication inter-processus (pipes, signaux, mémoire partagée) complètent le programme. Pour les examens marocains, les exercices d'ordonnancement avec diagramme de Gantt et les calculs de taux d'utilisation CPU sont systématiquement posés.",
        "key_exam_topics": ["Ordonnancement CPU : FCFS, SJF, Round Robin (diagramme de Gantt)", "Algorithme du banquier (évitement des deadlocks)", "Pagination et calcul d'adresse physique", "Synchronisation : sémaphores et problème producteur-consommateur", "Appels système Unix : fork(), exec(), pipe()"]
    },
    "Mathématiques pour l'Informatique (Logique & Graphes)": {
        "semester_hint": "S3",
        "prerequisites": ["Algèbre S1", "Analyse S2"],
        "description": "Ce module couvre deux grands axes mathématiques essentiels à l'informatique théorique. La logique propositionnelle et du premier ordre est étudiée : tables de vérité, formes normales conjonctives (FNC) et disjonctives (FND), résolution, et introduction à la logique de prédicats. La théorie des graphes constitue la deuxième partie majeure : représentations (matrice d'adjacence, listes d'adjacence), parcours en largeur (BFS) et profondeur (DFS), plus court chemin (Dijkstra, Bellman-Ford), arbres couvrants minimaux (Prim, Kruskal), et graphes orientés (DAGs). Pour les étudiants marocains, les exercices d'examen portent souvent sur l'exécution manuelle de Dijkstra ou Kruskal sur un graphe pondéré.",
        "key_exam_topics": ["Tables de vérité et simplification (Karnaugh)", "Parcours BFS et DFS avec tableau d'état", "Algorithme de Dijkstra : déroulé pas-à-pas", "Arbre couvrant minimal : Prim et Kruskal", "Détection de cycles dans un graphe orienté"]
    },
    "Architecture des Ordinateurs": {
        "semester_hint": "S3",
        "prerequisites": ["Électronique numérique S1"],
        "description": "Le module Architecture des Ordinateurs S3 approfondit les bases vues en première année. On étudie l'organisation interne d'un processeur : unité arithmétique et logique (ALU), registres, unité de contrôle, et le pipeline d'instructions (fetch-decode-execute). La hiérarchie mémoire est analysée en détail : registres, caches L1/L2/L3, RAM, et mémoire secondaire, avec les mécanismes de cohérence de cache. L'assembleur (x86 ou MIPS) est introduit pour comprendre les instructions machine, les modes d'adressage, et la gestion de la pile d'appel. Les bus système, les interruptions matérielles, et les entrées/sorties complètent le programme.",
        "key_exam_topics": ["Pipeline CPU : stalls, dépendances et forwarding", "Calcul de performance : CPI, MIPS, temps d'exécution", "Hiérarchie mémoire : taux de succès cache, temps d'accès moyen", "Assembleur MIPS/x86 : lecture et écriture de programmes simples", "Modes d'adressage : immédiat, registre, mémoire indirect"]
    },
    "Bases de Données (BD)": {
        "semester_hint": "S4",
        "prerequisites": ["Algorithmique S3", "Modélisation UML"],
        "description": "Le module Bases de Données est l'un des plus importants de la filière GI. Il couvre la conception de bases de données relationnelles via le modèle Entité-Association (E/A) et sa traduction en schéma relationnel normalisé (1FN, 2FN, 3FN, BCNF). Le langage SQL est enseigné de façon approfondie : DDL (CREATE, ALTER, DROP), DML (SELECT avec JOIN, GROUP BY, HAVING, sous-requêtes corrélées), et les contraintes d'intégrité. La partie PL/SQL (procédures stockées, fonctions, triggers, curseurs) est souvent l'élément différenciateur aux examens. Pour les examens marocains, les exercices portent sur la normalisation d'un schéma, l'écriture de requêtes SQL complexes, et l'implémentation d'un trigger PL/SQL.",
        "key_exam_topics": ["Modèle E/A vers schéma relationnel", "Normalisation : 1FN, 2FN, 3FN, BCNF", "Requêtes SQL avancées : JOIN, sous-requêtes, GROUP BY", "PL/SQL : procédures stockées, fonctions, triggers", "Transactions : ACID, niveaux d'isolation, verrous"]
    },
    "Programmation Orientée Objet (POO — Java)": {
        "semester_hint": "S4",
        "prerequisites": ["Prog I Langage C", "ASD S3"],
        "description": "Ce module introduit le paradigme de programmation orientée objet à travers le langage Java. Les quatre piliers — encapsulation, héritage, polymorphisme et abstraction — sont enseignés progressivement. Les classes, objets, constructeurs, méthodes, et la gestion de la visibilité (public, private, protected) constituent les bases. L'héritage simple et le polymorphisme (surcharge, redéfinition) sont pratiqués intensivement. Les interfaces et les classes abstraites permettent de concevoir des architectures flexibles. Les collections Java (ArrayList, HashMap, LinkedList) et la gestion des exceptions complètent le programme. Pour réussir les examens, maîtrisez les diagrammes de classes UML et leur implémentation directe en Java.",
        "key_exam_topics": ["Héritage et polymorphisme : redéfinition de méthodes", "Interfaces vs classes abstraites", "Collections Java : ArrayList, HashMap, Iterator", "Gestion des exceptions : hiérarchie et exceptions personnalisées", "Diagrammes de classes UML vers code Java"]
    },
    "Réseaux Informatiques": {
        "semester_hint": "S4",
        "prerequisites": ["Systèmes d'Exploitation S3", "Architecture des Ordinateurs"],
        "description": "Le module Réseaux Informatiques présente les principes de communication entre machines à travers le modèle OSI (7 couches) et le modèle TCP/IP (4 couches). La couche physique, la couche liaison de données (CSMA/CD, Ethernet), et la couche réseau (adressage IP, sous-réseaux CIDR, routage RIP, OSPF) sont détaillées. La couche transport distingue TCP (connexion orientée, contrôle de flux et congestion) et UDP (datagramme). Les protocoles applicatifs HTTP, DNS, DHCP, FTP sont étudiés. Les TP portent sur la configuration de Packet Tracer (Cisco) : VLAN, routage statique et dynamique, NAT. Pour les examens, maîtrisez le calcul de sous-réseaux CIDR.",
        "key_exam_topics": ["Modèle OSI et TCP/IP : rôle de chaque couche", "Adressage IP et calcul de sous-réseaux (CIDR)", "Protocoles TCP vs UDP : différences et cas d'utilisation", "Routage : RIP, OSPF, routage statique", "Configuration Cisco Packet Tracer : VLAN, NAT, DHCP"]
    },
    "Théorie des Langages et Compilation (TLC)": {
        "semester_hint": "S4",
        "prerequisites": ["Logique et Graphes S3", "Algorithmique S3"],
        "description": "Ce module fondamental traite de la théorie formelle des langages et de la construction des compilateurs. Les automates finis déterministes (AFD) et non-déterministes (AFND) sont introduits avec la conversion AFD↔AFND et la minimisation. Les expressions régulières et leur équivalence avec les automates finis sont démontrées. Les grammaires formelles (types 0–3 selon Chomsky) et les langages hors-contexte (CFG) sont couverts, avec les automates à pile (PDA). L'analyse lexicale, syntaxique et sémantique des compilateurs constituent la partie pratique. Pour les examens, pratiquez la construction d'un AFD depuis une expression régulière et déroulez un analyseur LL(1).",
        "key_exam_topics": ["Construction d'AFD depuis une expression régulière", "Conversion AFND → AFD (déterminisation)", "Grammaires hors-contexte (CFG) et arbres de dérivation", "Analyse syntaxique LL(1) : tables de prédiction", "Automates à pile (PDA) : reconnaissance de langages CFG"]
    },
    "Analyse Numérique": {
        "semester_hint": "S4",
        "prerequisites": ["Algèbre linéaire S2", "Analyse mathématique S2"],
        "description": "L'Analyse Numérique en S4 traite des méthodes algorithmiques pour résoudre des problèmes mathématiques continus. La résolution d'équations non-linéaires par les méthodes de bisection, Newton-Raphson, et la méthode de la sécante est étudiée. La résolution de systèmes linéaires utilise l'élimination de Gauss, la factorisation LU, et les méthodes itératives (Jacobi, Gauss-Seidel). L'interpolation polynomiale (Lagrange, Newton) et l'intégration numérique (trapèzes, Simpson, Gauss) complètent le programme. La résolution d'EDO par Euler et Runge-Kutta d'ordre 4 est également couverte.",
        "key_exam_topics": ["Méthode de Newton-Raphson : convergence et calcul", "Élimination de Gauss et factorisation LU", "Interpolation de Lagrange et de Newton", "Intégration numérique : Simpson, trapèzes (erreurs)", "Méthode de Runge-Kutta RK4 pour les EDO"]
    },
    "Technologie Web (TechnoWeb)": {
        "semester_hint": "S5",
        "prerequisites": ["POO Java S4", "Bases de Données S4", "Réseaux S4"],
        "description": "Le module Technologie Web forme les étudiants au développement d'applications web complètes. Côté client, HTML5 et CSS3 sont maîtrisés (flexbox, grid, responsive design). JavaScript ES6+ est enseigné en profondeur : manipulation du DOM, événements, fetch API, promesses, async/await. Côté serveur, PHP avec MySQL (PDO, requêtes préparées) ou Node.js est utilisé pour créer des APIs REST. La sécurité web est abordée : injections SQL, XSS, CSRF, et bonnes pratiques. Les sessions, cookies, l'authentification (JWT), et le déploiement sur Apache/Nginx complètent le programme. Pour les examens, sachez créer une application CRUD complète et expliquer les vulnérabilités XSS et SQL Injection.",
        "key_exam_topics": ["HTML5/CSS3 : mise en page responsive (flexbox/grid)", "JavaScript DOM : manipulation, événements, AJAX/fetch", "PHP : sessions, cookies, connexion PDO à MySQL", "REST API : conception et consommation avec JavaScript", "Sécurité web : SQL Injection, XSS, CSRF et prévention"]
    },
    "Intelligence Artificielle (IA)": {
        "semester_hint": "S5",
        "prerequisites": ["Algorithmique S3", "Probabilités et Statistiques S4"],
        "description": "Ce module introduit les fondements de l'intelligence artificielle classique et moderne. La recherche heuristique est couverte avec les algorithmes A*, BFS, DFS, et le minimax pour les jeux. L'apprentissage automatique (machine learning) introduit la régression linéaire et logistique, les arbres de décision (ID3, C4.5), les k-plus proches voisins, les SVM, et le clustering (k-means). Les réseaux de neurones artificiels (perceptron multicouche, rétropropagation) constituent une introduction au deep learning. La validation croisée et les métriques d'évaluation (précision, rappel, F1-score) sont enseignées. Utilisez scikit-learn et NumPy pour les TP.",
        "key_exam_topics": ["Algorithme A* : admissibilité de l'heuristique et déroulé", "Arbre de décision ID3 : calcul de l'entropie et gain d'information", "Régression logistique : fonction sigmoïde, descente de gradient", "Rétropropagation du gradient dans un réseau de neurones", "Évaluation de modèles : matrice de confusion, F1-score"]
    },
    "Génie Logiciel (GL)": {
        "semester_hint": "S5",
        "prerequisites": ["POO Java S4", "Bases de Données S4"],
        "description": "Le Génie Logiciel forme les étudiants aux méthodologies et outils de développement professionnel de logiciels. Les modèles de cycle de vie (cascade, V, itératif, agile Scrum/Kanban) sont comparés. La modélisation UML avancée couvre les diagrammes de cas d'utilisation, de classes, de séquences, d'activités, et d'états-transitions. Les patterns de conception (design patterns) GoF sont étudiés : Singleton, Factory, Observer, Strategy, MVC. Les tests logiciels (unitaires avec JUnit, TDD) et la gestion de configuration (Git, CI/CD) sont pratiqués. Pour les examens marocains, les exercices portent sur la modélisation UML d'un système donné et l'identification des patterns adaptés.",
        "key_exam_topics": ["Diagrammes UML : cas d'utilisation, classes, séquences", "Design Patterns GoF : Singleton, Factory, Observer, Strategy", "Architecture MVC : séparation des responsabilités", "Tests unitaires avec JUnit : mocks, assertions, TDD", "Méthodes Agile : Scrum, sprints, user stories, velocity"]
    },
    "Probabilités et Statistiques pour l'Informatique": {
        "semester_hint": "S5",
        "prerequisites": ["Analyse mathématique S2", "Algèbre S2"],
        "description": "Ce module fournit les outils mathématiques probabilistes et statistiques indispensables à l'informaticien moderne. Les espaces probabilisés, variables aléatoires discrètes et continues, lois classiques (binomiale, Poisson, normale, exponentielle) constituent les bases. Les théorèmes limites (loi des grands nombres, théorème central limite) et les intervalles de confiance permettent l'inférence statistique. La régression linéaire, les tests d'hypothèses (t-test, chi-deux, ANOVA), et la corrélation sont enseignés. La chaîne de Markov est introduite avec ses applications aux files d'attente. Pour les examens, les calculs de loi normale (table Z) et les intervalles de confiance sont systématiquement demandés.",
        "key_exam_topics": ["Loi normale : standardisation Z, lecture de table", "Intervalles de confiance : construction et interprétation", "Tests d'hypothèses : H0, H1, p-value, niveau de signification", "Régression linéaire : moindres carrés, coefficient R²", "Chaînes de Markov : matrice de transition, états absorbants"]
    },
    "Sécurité Informatique": {
        "semester_hint": "S6",
        "prerequisites": ["Réseaux S4", "Systèmes d'Exploitation S3", "Mathématiques (Algèbre)"],
        "description": "Le module Sécurité Informatique couvre les fondements de la cybersécurité appliquée aux systèmes d'information. La cryptographie symétrique (AES, DES) et asymétrique (RSA, Diffie-Hellman) sont enseignées avec leur base mathématique (arithmétique modulaire, théorème d'Euler). Les fonctions de hachage (SHA-256, MD5) et les signatures numériques garantissent l'intégrité. La sécurité réseau couvre les firewalls, VPN (IPSec, SSL/TLS), IDS/IPS, et les attaques classiques (MITM, DDoS). La sécurité applicative (OWASP Top 10), l'analyse de malware, et la forensique numérique sont abordées. Pour les examens, maîtrisez RSA de bout en bout et les modes opératoires de chiffrement par blocs.",
        "key_exam_topics": ["RSA : génération de clés, chiffrement et déchiffrement", "AES-CBC : chiffrement par blocs et vecteur d'initialisation", "Protocole SSL/TLS : handshake et certificats X.509", "Attaques réseaux : MITM, ARP poisoning, DDoS", "OWASP Top 10 : injections, XSS, IDOR et remédiation"]
    },
    "Systèmes Distribués et Cloud Computing": {
        "semester_hint": "S6",
        "prerequisites": ["Réseaux S4", "Systèmes d'Exploitation S3", "Bases de Données S4"],
        "description": "Ce module de fin de cycle traite des architectures modernes de systèmes informatiques répartis. Les paradigmes de communication distribuée (RPC, RMI Java, REST, gRPC, files de messages Kafka) sont étudiés. Le théorème CAP et les bases de données NoSQL (MongoDB, Cassandra, Redis) sont présentés. La conteneurisation avec Docker et l'orchestration avec Kubernetes constituent le cœur pratique. Les paradigmes cloud (IaaS, PaaS, SaaS) et les fournisseurs majeurs (AWS, GCP, Azure) sont couverts. La programmation parallèle et la tolérance aux pannes (réplication, consensus Raft/Paxos) complètent le programme.",
        "key_exam_topics": ["Théorème CAP : exemples de systèmes et compromis", "Docker : Dockerfile, docker-compose, réseaux de conteneurs", "NoSQL vs SQL : choix selon les contraintes ACID/BASE", "Architecture microservices vs monolithique", "Algorithme de consensus Raft : élection de leader"]
    },
}

# ══════════════════════════════════════════════════════════════════════════════
#  AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════

def authenticate() -> object:
    """
    Authenticate using Service Account (preferred for server use)
    or OAuth2 Desktop App flow (for local development).
    Returns an authenticated Google Drive service object.
    """
    creds = None

    # ── Option 1: Service Account ─────────────────────────────────────────────
    if SA_FILE.exists():
        print(f"🔑  Using Service Account: {SA_FILE}")
        creds = service_account.Credentials.from_service_account_file(
            str(SA_FILE), scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    # ── Option 2: OAuth2 Desktop App ─────────────────────────────────────────
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄  Refreshing expired OAuth2 token...")
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                raise FileNotFoundError(
                    f"\n❌  Neither '{SA_FILE.name}' nor '{CREDS_FILE.name}' found.\n"
                    "Please follow the SETUP instructions at the top of this script.\n"
                    "See README.md for detailed steps."
                )
            print(f"🌐  Launching OAuth2 browser flow from: {CREDS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next run
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"💾  Token saved to {TOKEN_FILE}")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ══════════════════════════════════════════════════════════════════════════════
#  CLASSIFICATION HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def classify_category(text: str) -> str:
    """Classify a file/folder name into COUR, TD, TP, or EXAMEN."""
    for category, pattern in CATEGORY_RULES:
        if pattern.search(text):
            return category
    return "COUR"  # default fallback


def classify_module(text: str) -> str | None:
    """Map a folder/file name to a canonical module name."""
    for pattern, canonical in MODULE_PATTERNS:
        if pattern.search(text):
            return canonical
    return None


def extract_year(text: str) -> str:
    """Extract academic year like '2023-2024' from a string."""
    m = YEAR_REGEX.search(text)
    if m:
        return m.group(1).replace("–", "-")
    return "General"


# ══════════════════════════════════════════════════════════════════════════════
#  DRIVE CRAWLER (RECURSIVE)
# ══════════════════════════════════════════════════════════════════════════════

def list_folder_contents(service, folder_id: str) -> list[dict]:
    """
    List all children (files and subfolders) of a Drive folder.
    Returns a list of Drive file metadata dicts.
    """
    items = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"
    fields = "nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink)"

    while True:
        resp = service.files().list(
            q=query,
            fields=fields,
            pageSize=200,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.1)  # polite rate-limit

    return items


def crawl_folder(
    service,
    folder_id: str,
    semester: str,
    path: list[str],
    resources: list[dict],
    stats: dict,
    depth: int = 0,
) -> None:
    """
    Recursively crawl a folder and populate the resources list.

    Context tracking:
      - path[0] is the root semester folder name
      - path[1] might be an academic year folder  "(2023-2024)"
      - path[2] might be a module folder
      - path[3+] might be a category subfolder (Cours, TD, TP, Examen)
    """
    indent = "  " * depth
    items = list_folder_contents(service, folder_id)
    print(f"{indent}📂  {' > '.join(path)} — {len(items)} items")
    stats["folders_visited"] += 1

    # Derive context from current path
    academic_year = "General"
    module_name   = None
    category      = None

    for segment in path:
        y = extract_year(segment)
        if y != "General":
            academic_year = y
        m = classify_module(segment)
        if m:
            module_name = m
        # Check if this segment itself is a category hint
        for cat, pat in CATEGORY_RULES:
            if pat.search(segment):
                category = cat
                break

    for item in items:
        name     = item["name"]
        mime     = item["mimeType"]
        file_id  = item["id"]
        is_dir   = mime == "application/vnd.google-apps.folder"

        if is_dir:
            crawl_folder(
                service,
                file_id,
                semester,
                path + [name],
                resources,
                stats,
                depth + 1,
            )
        else:
            # It's a file — determine metadata
            stats["files_found"] += 1

            # Module: inherit from path, or try filename
            final_module = module_name or classify_module(name) or "Module Inconnu"

            # Category: inherit from path, or classify from filename
            final_category = category or classify_category(name)

            # Academic year: inherit from path, or try filename
            final_year = academic_year
            y_from_name = extract_year(name)
            if y_from_name != "General":
                final_year = y_from_name

            record = {
                "major":         MAJOR,
                "semester":      semester,
                "academic_year": final_year,
                "module":        final_module,
                "category":      final_category,
                "title":         name,
                "drive_file_id": file_id,
                "embed_url":     f"https://drive.google.com/file/d/{file_id}/preview",
                "download_url":  f"https://drive.google.com/uc?export=download&id={file_id}",
                "mime_type":     mime,
                "web_view_link": item.get("webViewLink", ""),
                "modified_time": item.get("modifiedTime", ""),
                "folder_path":   " > ".join(path),
            }
            resources.append(record)
            print(f"{indent}  📄  [{final_category:6}] {name[:60]}")


# ══════════════════════════════════════════════════════════════════════════════
#  MODULE METADATA BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_modules_metadata(resources: list[dict]) -> list[dict]:
    """
    Build the modules_metadata array from discovered modules + pre-authored metadata.
    Also add any module from MODULES_METADATA not found in the crawl.
    """
    # Collect all unique (semester, module) pairs discovered
    discovered = {}
    for r in resources:
        key = (r["semester"], r["module"])
        if key not in discovered:
            discovered[key] = r["academic_year"]

    modules_meta = []
    seen_modules = set()

    # First: modules actually found in Drive
    for (semester, module_name), academic_year in sorted(discovered.items()):
        if module_name in seen_modules:
            continue
        seen_modules.add(module_name)

        pre = MODULES_METADATA.get(module_name, {})
        modules_meta.append({
            "major":            MAJOR,
            "semester":         semester,
            "academic_year":    academic_year,
            "module_name":      module_name,
            "prerequisites":    pre.get("prerequisites", []),
            "description":      pre.get("description", f"Module {module_name} — Génie Informatique {semester}."),
            "key_exam_topics":  pre.get("key_exam_topics", []),
        })

    # Then: pre-authored modules not found in Drive (editorial completeness)
    for module_name, meta in MODULES_METADATA.items():
        if module_name not in seen_modules:
            modules_meta.append({
                "major":            MAJOR,
                "semester":         meta.get("semester_hint", "General"),
                "academic_year":    "General",
                "module_name":      module_name,
                "prerequisites":    meta.get("prerequisites", []),
                "description":      meta.get("description", ""),
                "key_exam_topics":  meta.get("key_exam_topics", []),
                "_note":            "Module défini par éditorial — non trouvé dans le crawl Drive."
            })

    return modules_meta


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  Google Drive Crawler — Génie Informatique Portal")
    print("  Université Marocaine — Filière SMI/GI")
    print(f"  Started: {datetime.utcnow().isoformat()}Z")
    print("=" * 70)

    # 1. Authenticate
    service = authenticate()
    print("✅  Authenticated successfully.\n")

    resources = []
    stats = {"folders_visited": 0, "files_found": 0}

    # 2. Crawl each semester folder
    for semester, folder_id in SEMESTER_FOLDERS.items():
        print(f"\n{'─'*60}")
        print(f"🎓  Crawling Semester {semester} (folder: {folder_id})")
        print(f"{'─'*60}")
        crawl_folder(
            service,
            folder_id,
            semester,
            [semester],
            resources,
            stats,
            depth=0,
        )

    print(f"\n{'='*60}")
    print(f"  📊  CRAWL COMPLETE")
    print(f"  Folders visited : {stats['folders_visited']}")
    print(f"  Files found     : {stats['files_found']}")
    print(f"{'='*60}\n")

    # 3. Build modules metadata
    modules_metadata = build_modules_metadata(resources)

    # 4. Assemble final JSON
    output = {
        "_meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "major": MAJOR,
            "university": "Faculté des Sciences — Maroc",
            "total_files": stats["files_found"],
            "total_folders": stats["folders_visited"],
            "total_modules": len(modules_metadata),
            "source_folders": {k: f"https://drive.google.com/drive/folders/{v}"
                               for k, v in SEMESTER_FOLDERS.items()},
        },
        "modules_metadata": modules_metadata,
        "resources": resources,
    }

    # 5. Write JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅  Output written to: {OUTPUT_FILE}")
    print(f"    Modules   : {len(modules_metadata)}")
    print(f"    Resources : {len(resources)}")

    # 6. Print quick summary table
    print("\n📋  Module Summary:")
    print(f"  {'Semester':<6} {'Module':<50} {'Files':>5}")
    print(f"  {'─'*6} {'─'*50} {'─'*5}")
    module_counts: dict[tuple, int] = {}
    for r in resources:
        key = (r["semester"], r["module"])
        module_counts[key] = module_counts.get(key, 0) + 1
    for (sem, mod), count in sorted(module_counts.items()):
        print(f"  {sem:<6} {mod[:50]:<50} {count:>5}")

    print(f"\n🎉  Done! Open {OUTPUT_FILE.name} to use in your portal.")


if __name__ == "__main__":
    main()
