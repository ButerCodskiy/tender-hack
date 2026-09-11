#!/usr/bin/env python3
"""
21st.dev Component & Prompt Extractor
Извлекает метаданные, зависимости и чистый TSX исходный код с открытого CDN 21st.dev без регистрации и API-ключей.
"""

import sys
import re
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://21st.dev/",
}

def fetch_url(url: str) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return None

def extract_theme(slug: str, clean_url: str) -> Optional[Dict[str, Any]]:
    api_url = f'https://21st.dev/api/trpc/themes.getBySlug?batch=1&input=%7B%220%22%3A%7B%22json%22%3A%7B%22slug%22%3A%22{slug}%22%7D%7D%7D'
    raw_json = fetch_url(api_url) or ""
    try:
        data = json.loads(raw_json)
        theme_obj = data[0]['result']['data']['json']
        name = theme_obj.get('name', slug.title())
        styles = theme_obj.get('styles', {})
        return {
            "title": f"Theme: {name}",
            "description": f"Complete shadcn/ui color palette, typography and CSS tokens for {name}",
            "url": clean_url,
            "is_theme": True,
            "theme_name": name,
            "styles": styles,
        }
    except Exception:
        return None

def extract_component(page_url: str) -> Dict[str, Any]:
    clean_url = page_url.strip().split("?")[0].rstrip("/")
    if not clean_url.startswith("http"):
        clean_url = f"https://21st.dev/{clean_url.lstrip('/')}"
    
    slug = clean_url.split("/")[-1]

    # Проверка на раздел /themes/
    if "/themes/" in clean_url or clean_url.startswith("https://21st.dev/@themes"):
        theme_res = extract_theme(slug, clean_url)
        if theme_res:
            return theme_res
    
    # 1. Извлечение метаданных из .md эндпоинта
    md_url = clean_url + ".md"
    md_content = fetch_url(md_url) or ""
    
    deps = "framer-motion clsx tailwind-merge lucide-react"
    deps_match = re.search(r"npm dependencies:\s*(.*)", md_content, re.IGNORECASE)
    if deps_match and deps_match.group(1).strip():
        deps = deps_match.group(1).strip() + " clsx tailwind-merge"

    # 2. Извлечение HTML страницы для поиска CDN ассетов
    raw_html = fetch_url(clean_url) or ""
    # Полное разэкранирование JSON-потока Next.js для получения чистых URL
    html = raw_html.replace(r'\/', '/').replace(r'\"', '"').replace(r"\'", "'")
    
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
    title = title_match.group(1).split("|")[0].strip() if title_match else slug.replace("-", " ").title()

    desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
    description = desc_match.group(1).strip() if desc_match else ""

    # Хитрый универсальный алгоритм: собираем ВСЕ ссылки на CDN, а затем классифицируем их
    all_cdn_links = set(re.findall(r'https://cdn\.21st\.dev/[^\s"\'\\<>\|]+', html))
    
    cdn_demo_url = ""
    bundle_url = ""
    
    for link in all_cdn_links:
        clean_link = link.split('?')[0] # Убираем query параметры для анализа
        
        # Ищем TSX демо-код
        if clean_link.endswith('.tsx') or 'code.demo' in clean_link:
            cdn_demo_url = link
            
        # Ищем бандл с логикой
        if clean_link.endswith('.html') or 'bundle' in clean_link or 'bundled' in clean_link:
            bundle_url = link

    demo_code = fetch_url(cdn_demo_url) if cdn_demo_url else ""
    
    bundle_script = ""
    if bundle_url:
        bundle_html = fetch_url(bundle_url) or ""
        scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', bundle_html, re.DOTALL)
        if scripts:
            # Главный бандл компонента всегда содержит основной React-код (самый длинный скрипт)
            bundle_script = max(scripts, key=len).strip()

    # Поиск внешнего GitHub репозитория и Live Preview (актуально для шаблонов /templates/)
    github_links = list(set(re.findall(r'https://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+', html)))
    github_repos = [
        g.replace('\\', '').strip('\"\'') for g in github_links
        if not any(x in g for x in ['/sponsors', '/topics', '/login', '/signup', '/settings', '.png', '.jpg', '.jpeg', '/21st', 'github.com/features'])
    ]
    github_url = github_repos[0] if github_repos else ""

    iframe_previews = [p for p in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html) if 'google' not in p and 'cloudflare' not in p]
    preview_url = iframe_previews[0] if iframe_previews else ""

    # Fallback к pre/code если демо не найдено
    if not demo_code:
        code_blocks = re.findall(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL)
        for b in code_blocks:
            clean_b = re.sub(r"<[^>]+>", "", b).strip()
            if len(clean_b) > 80:
                demo_code = clean_b
                break

    is_template = "/templates/" in clean_url or (bool(github_url) and not bool(bundle_script) and not bool(demo_code))

    return {
        "title": title,
        "description": description,
        "url": clean_url,
        "is_template": is_template,
        "github_url": github_url,
        "preview_url": preview_url,
        "dependencies": deps,
        "demo_url": cdn_demo_url,
        "bundle_url": bundle_url,
        "demo_code": demo_code,
        "bundle_script": bundle_script,
    }

def format_theme_css(styles: Dict[str, Any]) -> str:
    light = styles.get("light", {})
    dark = styles.get("dark", {})
    
    def render_vars(d: Dict[str, Any], indent: str = "  ") -> str:
        lines = []
        for k, v in d.items():
            lines.append(f"{indent}--{k}: {v};")
        return "\n".join(lines)

    return f""":root {{
{render_vars(light, '  ')}
}}

.dark {{
{render_vars(dark, '  ')}
}}"""

def build_markdown_prompt(data: Dict[str, Any]) -> str:
    if data.get('is_theme'):
        css_content = format_theme_css(data.get('styles', {}))
        return f"""# Shadcn UI Theme: {data['theme_name']}
> {data['description']}

### 1. CSS Design Tokens (`src/index.css` or `globals.css`)
```css
{css_content}
```

### 2. Usage in Tailwind CSS
Вставьте эти CSS-переменные в корневой файл стилей вашего проекта (`src/index.css`).
Все компоненты shadcn/ui и Tailwind автоматически применят цветовую палитру **{data['theme_name']}** как для светлой, так и для темной темы.
"""

    if data.get('is_template') and data.get('github_url'):
        return f"""# Full Website Template: {data['title']}
> {data['description']}

### 1. Template Information
- **Live Preview:** {data.get('preview_url') or 'See 21st.dev page'}
- **GitHub Repository (Full Source Code):** {data['github_url']}
- **Catalog URL:** {data['url']}

### 2. Setup & Installation
```bash
# Clone the complete template source code repository
git clone {data['github_url']}

# Install dependencies and start local development server
npm install
npm run dev
```

### 3. Direct Access & Architecture
Полный исходный код данного шаблона (все страницы, компоненты, ассеты и стили) размещен в открытом репозитории:
[{data['github_url']}]({data['github_url']})
"""

    bundle_info = ""
    if data.get('bundle_script'):
        bundle_info = f"""
### 4. Compiled Component Logic & Subcomponents (Bundle)
> **ИНСТРУКЦИЯ ДЛЯ АГЕНТА:** Ниже приведен полный скомпилированный код компонента со всеми подкомпонентами, хуками и Framer Motion анимациями из бандла.
> Создай файл `src/components/ui/<component-name>.tsx`, восстанови чистый TSX/JSX из этого кода, типизируй пропсы и экспортируй компонент.

```javascript
{data['bundle_script']}
```
"""
    return f"""# Component: {data['title']}
> {data['description']}

### 1. Dependencies
```bash
npm install {data['dependencies']}
```

### 2. Utility Helper (`lib/utils.ts`)
```typescript
import {{ ClassValue, clsx }} from "clsx";
import {{ twMerge }} from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {{
  return twMerge(clsx(inputs));
}}
```

### 3. Usage & Demo Code (Example)
```tsx
{data['demo_code'] if data['demo_code'] else '// Demo code not found'}
```
{bundle_info}
"""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_component.py <21st.dev URL>")
        sys.exit(1)
        
    target_url = sys.argv[1]
    extracted = extract_component(target_url)
    
    if "--json" in sys.argv:
        print(json.dumps(extracted, ensure_ascii=False, indent=2))
    else:
        print(build_markdown_prompt(extracted))
