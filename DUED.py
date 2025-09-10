import requests
import base64
from typing import Optional, Tuple, Dict, Any
import time
from urllib.parse import quote

class GitHubAPI:
    """Класс для работы с GitHub API"""
    
    BASE_URL = "https://api.github.com"
    HEADERS = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'GitHub-Welcome-App/1.0'
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
    
    def make_request(self, url: str) -> Optional[Dict[str, Any]]:
        """Выполняет HTTP запрос с обработкой ошибок"""
        try:
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 404:
                return None
            response.raise_for_status()
            
            # Проверяем лимит запросов
            remaining = int(response.headers.get('X-RateLimit-Remaining', 1))
            if remaining == 0:
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(reset_time - time.time(), 0) + 1
                print(f"⚠️ Лимит запросов исчерпан. Ожидание {wait_time:.0f} секунд...")
                time.sleep(wait_time)
                return self.make_request(url)  # Рекурсивный вызов после ожидания
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка сети: {e}")
            return None
        except ValueError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            return None

class GitHubUserProcessor:
    """Класс для обработки информации о пользователях GitHub"""
    
    def __init__(self):
        self.api = GitHubAPI()
    
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о пользователе"""
        url = f"{GitHubAPI.BASE_URL}/users/{quote(username)}"
        return self.api.make_request(url)
    
    def get_user_repos(self, repos_url: str) -> Optional[list]:
        """Получает список репозиториев пользователя"""
        return self.api.make_request(repos_url)
    
    def get_readme_content(self, username: str, repo_name: str) -> str:
        """Получает содержимое README файла"""
        url = f"{GitHubAPI.BASE_URL}/repos/{quote(username)}/{quote(repo_name)}/readme"
        readme_data = self.api.make_request(url)
        
        if readme_data and 'content' in readme_data:
            try:
                return base64.b64decode(readme_data['content']).decode('utf-8')
            except (base64.binascii.Error, UnicodeDecodeError):
                return "❌ Ошибка декодирования README файла"
        
        return "README файл не найден"
    
    def find_best_repo(self, repos: list, username: str) -> Optional[Dict[str, Any]]:
        """Находит наиболее релевантный репозиторий"""
        if not repos:
            return None
        
        # Приоритет: репозиторий с именем пользователя
        for repo in repos:
            if repo['name'].lower() == username.lower():
                return repo
        
        # Затем ищем репозиторий с README
        for repo in repos:
            if repo['has_wiki'] or repo['description']:
                return repo
        
        # Возвращаем самый новый репозиторий
        return sorted(repos, key=lambda x: x.get('pushed_at', ''), reverse=True)[0]
    
    def get_user_repo_info(self, username: str) -> Tuple[Optional[Dict], str, Optional[str]]:
        """
        Получает информацию о репозитории пользователя и README файл
        """
        # Получаем информацию о пользователе
        user_data = self.get_user_info(username)
        if not user_data:
            return None, "Пользователь не найден", None
        
        # Получаем список репозиториев
        repos_data = self.get_user_repos(user_data['repos_url'])
        if not repos_data:
            return user_data, "У пользователя нет репозиториев", None
        
        # Находим лучший репозиторий
        personal_repo = self.find_best_repo(repos_data, username)
        if not personal_repo:
            return user_data, "Не удалось найти подходящий репозиторий", None
        
        # Получаем README
        readme_content = self.get_readme_content(username, personal_repo['name'])
        
        return user_data, readme_content, personal_repo['name']

def format_user_info(user_data: Dict[str, Any], repo_name: str) -> str:
    """Форматирует информацию о пользователе"""
    info_lines = [
        "=" * 60,
        f"🎉 Приветствуем, {user_data.get('name', user_data.get('login', 'Пользователь'))}!",
        f"📝 Биография: {user_data.get('bio', 'Не указана')}",
        f"📍 Местоположение: {user_data.get('location', 'Не указано')}",
        f"👥 Подписчики: {user_data.get('followers', 0)}",
        f"📊 Публичные репозитории: {user_data.get('public_repos', 0)}",
        f"🔗 Профиль: {user_data['html_url']}",
        f"📂 Репозиторий: {repo_name}",
        "=" * 60
    ]
    return "\n".join(info_lines)

def format_readme_preview(readme_content: str, max_length: int = 500) -> str:
    """Форматирует предпросмотр README"""
    if readme_content == "README файл не найден":
        return "❌ README файл не найден в репозитории"
    
    # Очищаем от лишних пробелов и переносов
    cleaned_content = ' '.join(readme_content.split())
    
    if len(cleaned_content) > max_length:
        preview = cleaned_content[:max_length] + "..."
        return f"{preview}\n... (показаны первые {max_length} символов из {len(cleaned_content)})"
    
    return cleaned_content

def process_user(username: str, processor: GitHubUserProcessor) -> bool:
    """
    Обрабатывает запрос для одного пользователя
    Возвращает True если обработка прошла успешно
    """
    print(f"\n🔍 Ищем пользователя {username} на GitHub...")
    
    user_data, readme_content, repo_name = processor.get_user_repo_info(username)
    
    if user_data is None:
        if readme_content == "Пользователь не найден":
            print(f"👋 Пользователь '{username}' не найден!")
        else:
            print(f"❌ {readme_content}")
        return False
    
    # Выводим информацию о пользователе
    print(format_user_info(user_data, repo_name))
    
    # Выводим содержимое README
    print("\n📖 Содержимое README файла:")
    print("-" * 40)
    print(format_readme_preview(readme_content))
    
    print("\n" + "=" * 60)
    print("✨ Приятного кодирования!")
    return True

def main():
    """Основная функция программы"""
    print("👋 Добро пожаловать в GitHub приветственную программу!")
    print("=" * 60)
    print("Введите 'exit', 'quit' или 'выход' для выхода из программы")
    print("=" * 60)
    
    processor = GitHubUserProcessor()
    processed_users = set()
    
    while True:
        try:
            username = input("\n🎯 Введите имя пользователя GitHub: ").strip()
            
            # Проверяем команды выхода
            if username.lower() in ['exit', 'quit', 'выход']:
                print("👋 До свидания!")
                break
                
            if not username:
                print("❌ Имя пользователя не может быть пустым!")
                continue
            
            # Проверяем, не обрабатывали ли уже этого пользователя
            if username.lower() in processed_users:
                print("⚠️ Этот пользователь уже был обработан ранее.")
                continue
            
            # Обрабатываем пользователя
            if process_user(username, processor):
                processed_users.add(username.lower())
                
        except KeyboardInterrupt:
            print("\n\n👋 Программа прервана пользователем. До свидания!")
            break
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")

if __name__ == "__main__":
    main()