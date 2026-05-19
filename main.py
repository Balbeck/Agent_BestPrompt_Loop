import json
import os
import re
import requests


#                 - - - [ Variables ] - - -
OLLAMA_BASE_URL = "http://localhost:11434"
MODEL = "mistral:latest"
MAX_ITERATIONS = 2

INPUTS_FOLDER = "./inputs"
OUTPUT_FILE = "./output/best_prompt.md"

INITIAL_PROMPT_FILE   = os.path.join(INPUTS_FOLDER, "initial_prompt.txt")
QUESTION_FILE         = os.path.join(INPUTS_FOLDER, "question.txt")
TEST_DOCUMENT_FILE    = os.path.join(INPUTS_FOLDER, "test_document.txt")
REQUIRED_ELEMENTS_FILE = os.path.join(INPUTS_FOLDER, "required_elements.txt")
#                 - - - - - - - - - - - -



def read_file(path: str) -> str:
    if not os.path.exists(path):
        print(f" ❌ [ Error ] - Fichier introuvable : {path}")
        exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()



def call_ollama(prompt: str, label: str) -> str:
    # Appel simple a Ollama, return la string de reponse
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False
    }

    try:
        print(f"🤖 [ {label} ] Envoi a {MODEL}...")
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    except requests.exceptions.ConnectionError:
        print(f" ❌ [ Error ] Impossible to connect to {OLLAMA_BASE_URL}")
        exit(1)
    except requests.exceptions.Timeout:
        print(f" ❌ [ Error ] {MODEL} did not respond on time (timeout 180s)")
        exit(1)
    except Exception as e:
        print(f" ❌ [ Error ] {e}")
        exit(1)



def generate_answer(current_prompt: str, question: str, document: str) -> str:
    # LLM 1 - GENERATION : current_prompt template + question + document
    try:
        filled = current_prompt.format(context=document, query=question)
    except (KeyError, IndexError):
        # Fallback si le prompt a perdu ses placeholders
        filled = f"{current_prompt}\n\n=== DOCUMENTS ===\n{document}\n\n=== QUESTION ===\n{question}"
    return call_ollama(filled, label="Generation")



def verify_answer(answer: str, required_elements: str) -> dict:
    # LLM 2 - VERIFICATION : retourne {} si tout OK, sinon {"missing": [...]}
    prompt = f"""
        Tu es un verificateur strict.
        On te donne une REPONSE produite par un assistant, et une liste d'ELEMENTS MINIMUM
        qui doivent obligatoirement apparaitre dans cette reponse.

        === REPONSE A VERIFIER ===
        {answer}
        === FIN REPONSE ===

        === ELEMENTS MINIMUM REQUIS ===
        {required_elements}
        === FIN ELEMENTS REQUIS ===

        INSTRUCTIONS :
        - Si TOUS les elements minimum sont bien presents dans la reponse, il nont pas besoin detre ecris precidsement de la meme maniere mais ils doivent apparaitre, retourne EXACTEMENT et UNIQUEMENT : {{}}
        - Sinon, retourne un objet JSON sous la forme : {{"missing": ["element manquant 1", "element manquant 2"]}}
        - Ne renvoie QUE le JSON, sans aucun texte autour, sans markdown, sans commentaire.

        REPONSE JSON :
    """
    raw = call_ollama(prompt, label="Verification")
    print(f" [ Verificateur - Answer ]\n{raw}\n")
    return parse_verification(raw)



def parse_verification(text: str) -> dict:
    # Extrait le 1er {...} de la reponse LLM et le parse en dict
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"missing": [f"(verificateur sans JSON valide : {text[:200]})"]}
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {"missing": [f"(JSON invalide : {text[:200]})"]}



def analyze_and_improve(current_prompt: str, missing: dict) -> str:
    # LLM 3 - ANALYSE : prend le prompt actuel + elements manquants, produit nouveau prompt
    prompt = f"""
        Tu es un expert en prompt engineering.
        On utilise un PROMPT pour faire repondre un LLM a une question sur un document.
        La reponse produite par ce prompt ne contient pas tous les elements requis.

        === PROMPT ACTUEL ===
        {current_prompt}
        === FIN PROMPT ACTUEL ===

        === ELEMENTS MANQUANTS DANS LA REPONSE ===
        {json.dumps(missing, ensure_ascii=False, indent=2)}
        === FIN ELEMENTS MANQUANTS ===

        INSTRUCTIONS :
        - Produis une NOUVELLE version du prompt qui permettra au LLM de faire apparaitre
          TOUS les elements manquants dans sa reponse.
        - Dans les modification que tu va effectuer pour produire le nouveau prompt, TU NE DOIS PAS Donner des instructions qui mentionnent precisement des element manquant de la reponse.
        - Ce prompt doit etre generique car doit pouvoir etre adape a dautres sujet ! les instructions a modifier ou ajouter devront sans doutes faire reference a l'exhaustivite.
        - Retourne UNIQUEMENT le nouveau prompt, sans guillemets, sans markdown, sans explication.

        NOUVEAU PROMPT :
    """
    return call_ollama(prompt, label="Analyse")



def save_best_prompt(prompt: str, iterations: int, converged: bool) -> None:
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"💾 Prompt ecrit dans {OUTPUT_FILE}")




if __name__ == "__main__":

    #  - [1] - [ Load inputs ] - - -
    current_prompt    = read_file(INITIAL_PROMPT_FILE)
    question          = read_file(QUESTION_FILE).strip()
    document          = read_file(TEST_DOCUMENT_FILE)
    required_elements = read_file(REQUIRED_ELEMENTS_FILE)

    print(f"🚀 Demarrage de la boucle (max {MAX_ITERATIONS} iterations)\n")

    converged = False

    #  - [2] - [ Loop : Generate -> Verify -> Analyse ] - - -
    for i in range(1, MAX_ITERATIONS + 1):
        print(f"\n=== Iteration {i}/{MAX_ITERATIONS} ===")

        # [A] Generation
        answer = generate_answer(current_prompt, question, document)
        print(f"📝 Reponse generee ({len(answer)} chars)")

        # [B] Verification
        verification = verify_answer(answer, required_elements)

        # [C] Parse : si {} -> on stoppe
        if verification == {}:
            print("✅ Tous les elements requis sont presents ! Convergence atteinte.")
            converged = True
            save_best_prompt(current_prompt, i, converged=True)
            break

        print(f"⚠️  Elements manquants : {verification}")

        # [D] Analyse -> nouveau prompt
        current_prompt = analyze_and_improve(current_prompt, verification)
        print(f"🔧 Nouveau prompt produit ({len(current_prompt)} chars)")

    #  - [3] - [ Fin sans convergence ] - - -
    if not converged:
        print(f"\n⏱️  MAX_ITERATIONS atteint ({MAX_ITERATIONS}) - la boucle n'a pas converge.")
        save_best_prompt(current_prompt, MAX_ITERATIONS, converged=False)
