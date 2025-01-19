import os
import re
import fitz
import base64
from dataclasses import dataclass
from typing import List, Dict, Optional
from langdetect import detect


@dataclass
class ChapterInfo:
    number: int
    title: str
    content: str
    coordinates: Optional[tuple] = None  # Ajouter les coordonnées du chapitre


@dataclass
class NovelMetadata:
    title: str
    language: str
    author: Optional[str] = None
    series: Optional[str] = None
    volume: Optional[str] = None


class NovelPatternMatcher:
    """Gère les patterns de reconnaissance pour différents formats de novels."""

    def __init__(self):
        self.patterns = {
            "fr": {
                "chapter": [
                    r"(?i)^chapitre\s*(\d+)\s*[:|\-|–]?\s*(.*)$",
                    r"(?i)^partie\s*(\d+)\s*[:|\-|–]?\s*(.*)$",
                ],
                "dialogue": ["—", "–", "-"],
                "section": [
                    r"(?i)^(prologue)\s*[:|\-|–]?\s*(.*)$",
                    r"(?i)^(épilogue)\s*[:|\-|–]?\s*(.*)$",
                ],
            },
            "en": {
                "chapter": [
                    r"(?i)^chapter\s*(\d+)\s*[:|\-|–]?\s*(.*)$",
                    r"(?i)^part\s*(\d+)\s*[:|\-|–]?\s*(.*)$",
                ],
                "dialogue": ['"', "'", '"', '"'],
                "section": [
                    r"(?i)^(prologue)\s*[:|\-|–]?\s*(.*)$",
                    r"(?i)^(epilogue)\s*[:|\-|–]?\s*(.*)$",
                ],
            },
            "ja": {
                "chapter": [
                    r"^第(\d+)章\s*[:|\-|–]?\s*(.*)$",
                    r"^(\d+)章\s*[:|\-|–]?\s*(.*)$",
                ],
                "dialogue": ["「", "」"],
                "section": [
                    r"^(プロローグ)\s*[:|\-|–]?\s*(.*)$",
                    r"^(エピローグ)\s*[:|\-|–]?\s*(.*)$",
                ],
            },
        }

    def get_patterns(self, language: str) -> Dict:
        """Retourne les patterns pour une langue donnée."""
        return self.patterns.get(language, self.patterns["en"])

    def detect_chapter(self, text: str, language: str) -> Optional[tuple]:
        """Détecte si une ligne est un chapitre."""
        patterns = self.get_patterns(language)["chapter"]
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                return match.groups()
        return None


class TextProcessor:
    def __init__(self, language: str):
        self.language = language
        self.pattern_matcher = NovelPatternMatcher()
        self.patterns = self.pattern_matcher.get_patterns(language)
        self.sentence_endings = {".", "!", "?", "...", "。", "！", "？"}

    def process_content(self, text: str) -> str:
        """Traite le contenu du texte en gérant dialogues et paragraphes."""
        lines = [line.strip() for line in text.split("\n") if self._is_valid_line(line)]
        paragraphs = []
        current_paragraph = ""
        in_dialogue = False

        for line in lines:
            # Vérifier si c'est un dialogue
            if self._is_dialogue_start(line):
                if current_paragraph and not in_dialogue:
                    paragraphs.append(self._wrap_paragraph(current_paragraph))
                    current_paragraph = ""
                in_dialogue = True
                current_paragraph += line + " "
            elif in_dialogue:
                current_paragraph += line + " "
                if self._is_sentence_end(line):
                    paragraphs.append(self._wrap_dialogue(current_paragraph))
                    current_paragraph = ""
                    in_dialogue = False
            else:
                current_paragraph += line + " "
                if self._is_sentence_end(line):
                    paragraphs.append(self._wrap_paragraph(current_paragraph))
                    current_paragraph = ""

        if current_paragraph:
            paragraphs.append(
                self._wrap_dialogue(current_paragraph)
                if in_dialogue
                else self._wrap_paragraph(current_paragraph)
            )

        return "\n".join(paragraphs)

    def _is_valid_line(self, line: str) -> bool:
        """Vérifie si une ligne doit être traitée."""
        if not line.strip():
            return False
        if line.startswith(("http://", "https://")):
            return False
        return True

    def _is_dialogue_start(self, line: str) -> bool:
        """Vérifie si la ligne commence par un marqueur de dialogue."""
        return any(
            line.strip().startswith(marker) for marker in self.patterns["dialogue"]
        )

    def _is_sentence_end(self, line: str) -> bool:
        """Vérifie si la ligne se termine par une fin de phrase."""
        return any(line.strip().endswith(end) for end in self.sentence_endings)

    def _wrap_paragraph(self, text: str) -> str:
        """Enveloppe le texte dans des balises de paragraphe."""
        return f"<div class='container paragraph'>{text.strip()}</div>"

    def _wrap_dialogue(self, text: str) -> str:
        """Enveloppe le texte dans des balises de dialogue."""
        return f"<div class='container dialogue'>{text.strip()}</div>"


class NovelConverter:
    def __init__(self, metadata: NovelMetadata):
        self.metadata = metadata
        self.elements = []  # Va contenir tous les éléments (texte et images) avec leurs coordonnées
        self.processor = TextProcessor(metadata.language)
        self.pattern_matcher = NovelPatternMatcher()

    def process_pdf(self, pdf_path: str) -> None:
        """Traite le PDF et extrait le contenu et les images."""
        doc = fitz.open(pdf_path)
        try:
            self._extract_content(doc)
            self._extract_images(doc)
        finally:
            doc.close()

    def _extract_content(self, doc) -> None:
        """Extrait le contenu textuel du PDF avec le numéro de page."""
        current_chapter = []
        chapter_number = 0
        current_page_number = 0

        for page in doc:
            current_page_number += 1
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if block['type'] == 0:  # Text block
                    text_line = ""
                    for line in block["lines"]:
                        text_line += " ".join([span['text'] for span in line["spans"]]) + " "
                    
                    text_line = text_line.strip()
                    if not text_line:
                        continue

                    chapter_match = self.pattern_matcher.detect_chapter(
                        text_line, self.metadata.language
                    )

                    if chapter_match:
                        # Sauvegarder le chapitre précédent
                        if current_chapter:
                            self._add_chapter_to_elements(chapter_number, current_chapter)
                        
                        chapter_number = int(chapter_match[0])
                        current_chapter = [{
                            'content': chapter_match[1] if chapter_match[1] else "",
                            'page': current_page_number,
                            'type': 'chapter_title'
                        }]
                    else:
                        current_chapter.append({
                            'content': text_line,
                            'page': current_page_number,
                            'type': 'text'
                        })

        # Sauvegarder le dernier chapitre
        if current_chapter:
            self._add_chapter_to_elements(chapter_number, current_chapter)

    def _add_chapter_to_elements(self, number: int, chapter_content: List[dict]) -> None:
        """Ajoute les éléments du chapitre à la liste principale."""
        for element in chapter_content:
            self.elements.append({
                'chapter_number': number,
                'type': element['type'],
                'content': element['content'],
                'page': element['page']
            })

    def _save_chapter(self, number: int, content: List[tuple]) -> None:
        """Sauvegarde un chapitre traité avec ses coordonnées."""
        title, coordinates = content[0]
        processed_content = "\n".join([self.processor.process_content(line, coords) for line, coords in content[1:]])
        self.chapters.append({
            'number': number,
            'title': title,
            'content': processed_content,
            'coordinates': coordinates
        })

    def _extract_images(self, doc) -> None:
        """Extrait les images avec leur numéro de page."""
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)

            for img_idx, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]

                    # Vérifier la taille minimale
                    if len(image_bytes) < 10000:  # Ignorer les petites images
                        continue

                    img_data = base64.b64encode(image_bytes).decode("utf-8")
                    self.elements.append({
                        'type': 'image',
                        'data': f"data:image/jpeg;base64,{img_data}",
                        'alt': f"Image {page_num+1}-{img_idx+1}",
                        'page': page_num + 1
                    })
                except Exception as e:
                    print(f"Erreur lors de l'extraction de l'image: {e}")

    def save_html(self, output_path: str) -> None:
        """Génère et sauve le fichier HTML final."""
        html_content = self._generate_html()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    def _generate_html(self) -> str:
        """Génère le HTML en regroupant les éléments par page."""
        # Trier les éléments par numéro de page
        sorted_elements = sorted(self.elements, key=lambda x: x['page'])
        
        containers = []
        current_container = []
        current_page = sorted_elements[0]['page'] if sorted_elements else 1
        
        for element in sorted_elements:
            # Si on change de page ou si la page a changé de +/- 1
            if abs(element['page'] - current_page) > 1:
                if current_container:
                    containers.append(self._create_container(current_container))
                    current_container = []
                current_page = element['page']
            
            current_container.append(element)
            
        # Ajouter le dernier container
        if current_container:
            containers.append(self._create_container(current_container))
            
        return self._get_html_template().format(
            title=self.metadata.title,
            language=self.metadata.language,
            content="\n".join(containers)
        )

    def _create_container(self, elements: List[dict]) -> str:
        """Crée un conteneur HTML pour un groupe d'éléments."""
        content = []
        
        for element in elements:
            if element['type'] == 'chapter_title':
                content.append(f'<h2 class="chapter-title">Chapter {element.get("chapter_number")}: {element["content"]}</h2>')
            elif element['type'] == 'text':
                processed_text = self.processor.process_content(element['content'])
                content.append(processed_text)
            elif element['type'] == 'image':
                content.append(f'''
                    <div class="image-wrapper">
                        <img src="{element['data']}" alt="{element['alt']}">
                    </div>
                ''')
        
        return f'''
            <div class="container">
                {"".join(content)}
            </div>
        '''
    
    def _get_html_template(self) -> str:
        """Retourne le template HTML avec les styles."""
        return """<!DOCTYPE html>
            <html lang="{language}">
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
                    
                    .container {{
                        max-width: 800px;
                        margin: 1.5rem auto;
                        padding: 1rem;
                        background-color: rgba(255,255,255,0.05);
                        border-radius: 8px;
                    }}
                    
                    .container.paragraph {{
                        margin-bottom: 1.5rem;
                        text-align: justify;
                    }}
                    
                    .container.dialogue {{
                        margin: 1.5rem auto;
                        padding: 1rem;
                        background-color: rgba(255,255,255,0.1);
                        border-left: 4px solid var(--link-color);
                        font-style: italic;
                    }}
                    
                    .chapter-title {{
                        color: var(--link-color);
                        margin: 2rem 0 1rem 0;
                        font-size: 1.5rem;
                        text-align: center;
                    }}
                    
                    .image-wrapper {{
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        margin: 2rem 0;
                    }}
                    
                    .image-wrapper img {{
                        max-width: 100%;
                        height: auto;
                        border-radius: 8px;
                    }}
                    
                    @media (max-width: 768px) {{
                        .container {{
                            margin: 1rem;
                            padding: 0.5rem;
                        }}
                    }}
                </style>
            </head>
            <body>
                {content}
            </body>
            </html>"""
    
def convert_novel(pdf_path: str, output_path: str, title: str = None) -> bool:
    """Fonction principale pour convertir un novel PDF en HTML."""
    try:
        # Détecter la langue du document
        doc = fitz.open(pdf_path)
        sample_text = ""
        for page in range(min(5, len(doc))):  # Échantillon des 5 premières pages
            sample_text += doc[page].get_text()
        doc.close()

        detected_language = detect(sample_text)[
            :2
        ]  # Prendre les 2 premiers caractères (fr, en, ja, etc.)

        # Créer les métadonnées
        metadata = NovelMetadata(
            title=title or os.path.splitext(os.path.basename(pdf_path))[0],
            language=detected_language,
        )

        # Initialiser et utiliser le convertisseur
        converter = NovelConverter(metadata)
        converter.process_pdf(pdf_path)
        converter.save_html(output_path)

        return True
    except Exception as e:
        print(f"Erreur lors de la conversion: {e}")
        return False


# Utilisation simple
success = convert_novel(
    "./input/Mushoku Tensei - Jobless Reincarnation Volume-15.pdf",
    "./output/Mushoku Tensei - Jobless Reincarnation Volume-15.html",
    "Mushoku Tensei",
)

# Ou avec plus de contrôle
metadata = NovelMetadata(
    title="Mushoku Tensei",
    language="fr",
    author="Rifujin na Magonote",
    volume="Tome 16",
)
converter = NovelConverter(metadata)
converter.process_pdf("./input/Mushoku Tensei - Jobless Reincarnation Volume-15.pdf")
converter.save_html("./output/Mushoku Tensei - Jobless Reincarnation Volume-15.html")

