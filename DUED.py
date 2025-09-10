import requests
import base64
from typing import Optional, Tuple, Dict, Any, List
import time
from urllib.parse import quote
from datetime import datetime, timedelta
from collections import defaultdict
import calendar

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
    
    def make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Выполняет HTTP запрос с обработкой ошибок"""
        try:
            response = self.session.get(url, params=params, timeout=15)
            
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
                return self.make_request(url, params)
            
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
    
    def get_user_events(self, username: str) -> Optional[list]:
        """Получает события пользователя за последний год"""
        one_year_ago = (datetime.now() - timedelta(days=365)).isoformat()
        url = f"{GitHubAPI.BASE_URL}/users/{quote(username)}/events"
        params = {'per_page': 100}  # Максимальное количество событий на страницу
        return self.api.make_request(url, params)
    
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
    
    def analyze_activity(self, events: List[Dict]) -> Dict[str, Any]:
        """Анализирует активность пользователя за последний год"""
        if not events:
            return {
                'total_events': 0,
                'monthly_activity': defaultdict(int),
                'activity_by_type': defaultdict(int),
                'last_activity': None
            }
        
        monthly_activity = defaultdict(int)
        activity_by_type = defaultdict(int)
        last_activity = None
        
        for event in events:
            try:
                event_date = datetime.strptime(event['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                month_key = event_date.strftime('%Y-%m')
                monthly_activity[month_key] += 1
                
                event_type = event['type']
                activity_by_type[event_type] += 1
                
                if last_activity is None or event_date > last_activity:
                    last_activity = event_date
                    
            except (KeyError, ValueError):
                continue
        
        return {
            'total_events': len(events),
            'monthly_activity': dict(monthly_activity),
            'activity_by_type': dict(activity_by_type),
            'last_activity': last_activity
        }
    
    def get_activity_summary(self, activity_data: Dict) -> str:
        """Форматирует сводку активности"""
        if activity_data['total_events'] == 0:
            return "❌ Нет активности за последний год"
        
        summary = []
        summary.append(f"📊 Всего событий: {activity_data['total_events']:,}")
        
        # Топ-5 самых активных месяцев
        top_months = sorted(activity_data['monthly_activity'].items(), 
                          key=lambda x: x[1], reverse=True)[:5]
        if top_months:
            summary.append("📅 Самые активные месяцы:")
            for month, count in top_months:
                year, month_num = month.split('-')
                month_name = calendar.month_name[int(month_num)]
                summary.append(f"   • {month_name} {year}: {count} событий")
        
        # Топ-5 типов активности
        top_activities = sorted(activity_data['activity_by_type'].items(),
                              key=lambda x: x[1], reverse=True)[:5]
        if top_activities:
            summary.append("🎯 Основные активности:")
            for activity_type, count in top_activities:
                summary.append(f"   • {self.format_event_type(activity_type)}: {count}")
        
        if activity_data['last_activity']:
            last_active = activity_data['last_activity'].strftime('%d.%m.%Y %H:%M')
            summary.append(f"⏰ Последняя активность: {last_active}")
        
        return "\n".join(summary)
    
    def format_event_type(self, event_type: str) -> str:
        """Форматирует тип события для читаемости"""
        event_names = {
            'PushEvent': 'Push в репозиторий',
            'CreateEvent': 'Создание репозитория',
            'WatchEvent': 'Добавление в избранное',
            'ForkEvent': 'Форк репозитория',
            'PullRequestEvent': 'Pull Request',
            'IssuesEvent': 'Работа с issues',
            'CommitCommentEvent': 'Комментарии к коммитам',
            'DeleteEvent': 'Удаление',
            'ReleaseEvent': 'Релизы'
        }
        return event_names.get(event_type, event_type)
    
    def get_user_repo_info(self, username: str) -> Tuple[Optional[Dict], str, Optional[str], Optional[Dict]]:
        """
        Получает информацию о репозитории пользователя, README и активность
        """
        # Получаем информацию о пользователе
        user_data = self.get_user_info(username)
        if not user_data:
            return None, "Пользователь не найден", None, None
        
        # Получаем список репозиториев
        repos_data = self.get_user_repos(user_data['repos_url'])
        if not repos_data:
            return user_data, "У пользователя нет репозиториев", None, None
        
        # Находим лучший репозиторий
        personal_repo = self.find_best_repo(repos_data, username)
        if not personal_repo:
            return user_data, "Не удалось найти подходящий репозиторий", None, None
        
        # Получаем README
        readme_content = self.get_readme_content(username, personal_repo['name'])
        
        # Получаем и анализируем активность
        events = self.get_user_events(username)
        activity_data = self.analyze_activity(events) if events else None
        
        return user_data, readme_content, personal_repo['name'], activity_data

def format_date(github_date: str) -> str:
    """Форматирует дату из GitHub в читаемый вид"""
    try:
        date_obj = datetime.strptime(github_date, '%Y-%m-%dT%H:%M:%SZ')
        return date_obj.strftime('%d.%m.%Y')
    except (ValueError, TypeError):
        return "Неизвестно"

def format_user_info(user_data: Dict[str, Any], repo_name: str, activity_data: Optional[Dict] = None) -> str:
    """Форматирует информацию о пользователе"""
    # Получаем и форматируем дату регистрации
    joined_date = format_date(user_data.get('created_at'))
    
    info_lines = [
        "=" * 70,
        f"🎉 Приветствуем, {user_data.get('name', user_data.get('login', 'Пользователь'))}!",
        f"📝 Биография: {user_data.get('bio', 'Не указана')}",
        f"📍 Местоположение: {user_data.get('location', 'Не указано')}",
        f"📅 Присоединился к GitHub: {joined_date}",
        f"👥 Подписчики: {user_data.get('followers', 0):,}",
        f"📈 Подписки: {user_data.get('following', 0):,}",
        f"📊 Публичные репозитории: {user_data.get('public_repos', 0):,}",
        f"🔗 Профиль: {user_data['html_url']}",
        f"📂 Репозиторий: {repo_name}",
    ]
    
    # Добавляем информацию об активности, если есть
    if activity_data and activity_data['total_events'] > 0:
        info_lines.append(f"📈 Активность за год: {activity_data['total_events']:,} событий")
    
    info_lines.append("=" * 70)
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
    
    user_data, readme_content, repo_name, activity_data = processor.get_user_repo_info(username)
    
    if user_data is None:
        if readme_content == "Пользователь не найден":
            print(f"👋 Пользователь '{username}' не найден!")
        else:
            print(f"❌ {readme_content}")
        return False
    
    # Выводим информацию о пользователе
    print(format_user_info(user_data, repo_name, activity_data))
    
    # Выводим анализ активности
    if activity_data:
        print("\n📊 Анализ активности за последний год:")
        print("-" * 40)
        print(processor.get_activity_summary(activity_data))
    
    # Выводим содержимое README
    print("\n📖 Содержимое README файла:")
    print("-" * 40)
    print(format_readme_preview(readme_content))
    
    print("\n" + "=" * 70)
    print("✨ Приятного кодирования!")
    return True

def main():
    """Основная функция программы"""
    print("👋 Добро пожаловать в GitHub приветственную программу!")
    print("=" * 70)
    print("📊 Теперь с анализом активности за последний год!")
    print("Введите 'exit', 'quit' или 'выход' для выхода из программы")
    print("=" * 70)
    
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