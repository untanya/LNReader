import os
from PyPDF2 import PdfReader
from bs4 import BeautifulSoup
import base64
from PIL import Image
from io import BytesIO
import fitz  # PyMuPDF pour extraire les images
import re


class LightNovelConverter:
    def __init__(self, title):
        self.title = title
        self.chapters = []
        self.images = []

    def add_chapter(self, number, title, content):
        self.chapters.append({"number": number, "title": title, "content": content})

    def add_image(self, image_data, alt_text=""):
        try:
            img_data = base64.b64encode(image_data).decode("utf-8")
            self.images.append(
                {"data": f"data:image/jpeg;base64,{img_data}", "alt": alt_text}
            )
        except Exception as e:
            print(f"Erreur lors du chargement de l'image: {e}")

    def generate_html(self):
        # HTML Template reste le même que dans votre code original
        html_template = """
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                :root {{
                    --bg-color: #1a1a1a;
                    --text-color: #e0e0e0;
                    --header-bg: #2d2d2d;
                    --link-color: #66b3ff;
                }}
                
                body {{
                    background-color: var(--bg-color);
                    color: var(--text-color);
                    font-family: 'Arial', sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 0;
                }}
                
                .header {{
                    background-color: var(--header-bg);
                    padding: 1rem;
                    position: sticky;
                    top: 0;
                    z-index: 100;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                }}
                
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 1rem;
                }}
                
                .chapter {{
                    margin-bottom: 2rem;
                    padding: 1rem;
                    background-color: rgba(255,255,255,0.05);
                    border-radius: 8px;
                }}
                
                .chapter-title {{
                    color: var(--link-color);
                    margin-bottom: 1rem;
                }}
                
                .toc {{
                    margin: 2rem 0;
                    padding: 1rem;
                    background-color: var(--header-bg);
                    border-radius: 8px;
                }}
                
                .toc-item {{
                    color: var(--link-color);
                    text-decoration: none;
                }}
                
                .toc-item:hover {{
                    text-decoration: underline;
                }}
                
                img {{
                    max-width: 100%;
                    height: auto;
                    border-radius: 8px;
                    margin: 1rem 0;
                }}
                
                p {{
                    margin-bottom: 1.5em;
                    text-align: justify;
                }}
                
                blockquote {{
                    margin: 1.5rem 0;
                    padding: 1rem;
                    background-color: rgba(255, 255, 255, 0.1);
                    border-left: 4px solid var(--link-color);
                    font-style: italic;
                    color: var(--text-color);
                }}
                
                @media (max-width: 768px) {{
                    .container {{
                        padding: 0.5rem;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="container">
                    <h1>{title}</h1>
                </div>
            </div>
            
            <div class="container">
                <div class="toc">
                    <h2>Table des matières</h2>
                    <ul>
                        {toc}
                    </ul>
                </div>
                
                {content}
            </div>
        </body>
        </html>
        """

        # Générer la table des matières et le contenu comme dans votre code original
        toc = ""
        for chapter in self.chapters:
            toc += f'<li><a class="toc-item" href="#chapter-{chapter["number"]}">{chapter["title"]}</a></li>\n'

        content = ""
        for i, chapter in enumerate(self.chapters):
            content += f"""
            <div class="chapter" id="chapter-{chapter['number']}">
                <h2 class="chapter-title">{chapter['title']}</h2>
                {chapter['content']}
            </div>
            """
            if i < len(self.images):
                content += f'<img src="{self.images[i]["data"]}" alt="{self.images[i]["alt"]}">'

        return html_template.format(title=self.title, toc=toc, content=content)

    def save_html(self, output_path):
        # Créer le dossier de sortie s'il n'existe pas
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        html = self.generate_html()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Page HTML générée avec succès: {output_path}")


def process_page_content(text):
    """Nettoie et formate le texte extrait du PDF."""
    # Supprimer les lignes vides et les footers
    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip() and not line.startswith("https://")
    ]

    # Joindre les lignes en paragraphes
    paragraphs = []
    current_paragraph = ""

    for line in lines:
        if line.endswith(".") or line.endswith("!") or line.endswith("?"):
            current_paragraph += line + " "
            paragraphs.append(current_paragraph.strip())
            current_paragraph = ""
        else:
            current_paragraph += line + " "

    if current_paragraph:
        paragraphs.append(current_paragraph.strip())

    # Entourer chaque paragraphe avec des balises <p>
    formatted_paragraphs = [f"<p>{p}</p>" for p in paragraphs]

    # Joindre les paragraphes formatés
    formatted_text = "\n".join(formatted_paragraphs)

    # Identifier des citations ou dialogues et les formater comme un blockquote
    formatted_text = formatted_text.replace("Citation:", "<blockquote>").replace(
        "Fin Citation", "</blockquote>"
    )

    return formatted_text


def extract_chapters(text):
    """Extrait les chapitres du texte."""
    chapters = []
    current_chapter = ""
    current_title = ""

    lines = text.split("\n")
    in_chapter = False

    for line in lines:
        if "Chapitre" in line and ":" in line:
            # Si on était déjà dans un chapitre, on l'ajoute à la liste
            if in_chapter:
                chapters.append((current_title, current_chapter))

            current_title = line.strip()
            current_chapter = ""
            in_chapter = True
        elif in_chapter:
            current_chapter += line + "\n"  # Conserver les sauts de ligne

    # Ajouter le dernier chapitre
    if in_chapter:
        chapters.append((current_title, current_chapter))

    return chapters


def convert_ln_to_html(input_file, output_file):
    """Fonction principale pour convertir le light novel en HTML"""
    ln = LightNovelConverter("Mushoku Tensei (LN) – Tome 15")

    try:
        # Ouvrir le PDF avec PyMuPDF
        pdf_document = fitz.open(input_file)

        # Extraire le texte
        full_text = ""
        for page in pdf_document:
            full_text += page.get_text()

        # Extraire les chapitres
        chapters = extract_chapters(full_text)

        # Ajouter les chapitres au convertisseur
        for i, (title, content) in enumerate(chapters, 1):
            formatted_content = process_page_content(content)
            ln.add_chapter(i, title, formatted_content)

        # Extraire les images
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            image_list = page.get_images()

            for image_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = pdf_document.extract_image(xref)
                    image_data = base_image["image"]

                    ln.add_image(image_data, f"Image {page_num+1}-{image_index+1}")
                except Exception as e:
                    print(
                        f"Erreur lors de l'extraction de l'image {page_num+1}-{image_index+1}: {e}"
                    )

        # Fermer le PDF
        pdf_document.close()

        # Générer le fichier HTML
        ln.save_html(output_file)

    except Exception as e:
        print(f"Une erreur est survenue: {e}")
        return False

    return True


if __name__ == "__main__":
    # Exemple d'utilisation
    input_file = "./input/Mushoku Tensei (LN) – Tome 15.pdf"
    output_file = "./output/Mushoku Tensei (LN) - Tome 15.html"

    if convert_ln_to_html(input_file, output_file):
        print("Conversion terminée avec succès!")
    else:
        print("La conversion a échoué.")
