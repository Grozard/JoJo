import requests
import base64
from typing import Optional, Tuple, Dict, Any, List, Union, Callable
import time
from urllib.parse import quote, urljoin
from datetime import datetime, timedelta
from collections import defaultdict
import calendar
import re
import logging
from dataclasses import dataclass
from functools import lru_cache, wraps
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Декоратор для повторных попыток выполнения функции"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(f"Превышено количество попыток ({max_retries}) для {func.__name__}: {e}")
                        raise
                    
                    logger.warning(f"Попытка {retries}/{max_retries} не удалась для {func.__name__}: {e}. Повтор через {current_delay}с")
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper
    return decorator


@dataclass
class RateLimitInfo:
    """Информация о лимитах запросов"""
    remaining: int = 5000
    reset: float = 0.0
    used: int = 0
    limit: int = 5000


class GitHubAPI:
    """Класс для работы с GitHub API с улучшенной обработкой ошибок и пагинацией"""
    
    BASE_URL = "https://api.github.com"
    DEFAULT_HEADERS = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'GitHub-Welcome-App/1.0'
    }
    
    def __init__(self, token: Optional[str] = None):
        self.session = requests.Session()
        headers = self.DEFAULT_HEADERS.copy()
        if token:
            headers['Authorization'] = f'Bearer {token}'  # Используем Bearer token
        self.session.headers.update(headers)
        self.rate_limit = RateLimitInfo()
        self.last_request_time = 0.0
        self.min_request_interval = 0.1  # Минимальный интервал между запросами
    
    def _handle_rate_limit(self, response_headers: Dict[str, str]) -> None:
        """Обрабатывает информацию о лимите запросов"""
        if 'X-RateLimit-Remaining' in response_headers:
            self.rate_limit.remaining = int(response_headers['X-RateLimit-Remaining'])
        if 'X-RateLimit-Reset' in response_headers:
            self.rate_limit.reset = float(response_headers['X-RateLimit-Reset'])
        if 'X-RateLimit-Limit' in response_headers:
            self.rate_limit.limit = int(response_headers['X-RateLimit-Limit'])
        if 'X-RateLimit-Used' in response_headers:
            self.rate_limit.used = int(response_headers['X-RateLimit-Used'])
    
    def _check_rate_limit(self) -> None:
        """Проверяет и соблюдает лимит запросов"""
        current_time = time.time()
        
        # Соблюдаем минимальный интервал между запросами
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last_request)
        
        # Проверяем лимит запросов
        if self.rate_limit.remaining <= 5:  # Буфер безопасности
            wait_time = max(self.rate_limit.reset - current_time, 0) + 1
            if wait_time > 0:
                logger.warning(f"Приближаемся к лимиту запросов. Ожидание {wait_time:.0f} секунд...")
                time.sleep(wait_time)
    
    @retry(max_retries=3, delay=1.0, backoff=2.0)
    def make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Union[Dict[str, Any], List[Dict]]]:
        """Выполняет HTTP запрос с улучшенной обработкой ошибок и пагинацией"""
        self._check_rate_limit()
        
        try:
            if not url.startswith('http'):
                url = urljoin(self.BASE_URL, url)
            
            response = self.session.get(url, params=params, timeout=15)
            self.last_request_time = time.time()
            self._handle_rate_limit(response.headers)
            
            if response.status_code == 404:
                logger.debug(f"Ресурс не найден: {url}")
                return None
            elif response.status_code == 403:
                if 'rate limit' in response.text.lower():
                    reset_time = self.rate_limit.reset
                    wait_time = max(reset_time - time.time(), 0) + 1
                    logger.warning(f"Лимит запросов исчерпан. Ожидание {wait_time:.0f} секунд...")
                    time.sleep(wait_time)
                    return self.make_request(url, params)
                else:
                    logger.error(f"Доступ запрещен: {response.text}")
                    return None
            
            response.raise_for_status()
            
            # Обработка пагинации
            if 'next' in response.links and isinstance(response.json(), list):
                next_page = self.make_request(response.links['next']['url'])
                if next_page:
                    return response.json() + next_page
            
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.error(f"Таймаут при запросе к {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Ошибка соединения. Проверьте интернет-подключение.")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP ошибка: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети: {e}")
            return None
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return None


class GitHubUserProcessor:
    """Класс для обработки информации о пользователях GitHub с улучшенной логикой"""
    
    README_FILES = ['README.md', 'README.rst', 'README.txt', 'README', 'readme.md']
    EVENT_TYPE_MAPPING = {
        'PushEvent': 'Push в репозиторий',
        'CreateEvent': 'Создание репозитория/ветки',
        'WatchEvent': 'Добавление в избранное',
        'ForkEvent': 'Форк репозитория',
        'PullRequestEvent': 'Pull Request',
        'PullRequestReviewEvent': 'Ревью PR',
        'IssuesEvent': 'Работа с issues',
        'IssueCommentEvent': 'Комментарии к issues',
        'CommitCommentEvent': 'Комментарии к коммитам',
        'DeleteEvent': 'Удаление',
        'ReleaseEvent': 'Релизы',
        'GollumEvent': 'Изменения Wiki',
        'MemberEvent': 'Управление участниками',
        'PublicEvent': 'Публикация репозитория'
    }
    
    def __init__(self, github_token: Optional[str] = None):
        self.api = GitHubAPI(github_token)
        self._cache: Dict[str, Any] = {}
    
    def clear_cache(self) -> None:
        """Очищает кэш"""
        self._cache.clear()
    
    def _get_cached_or_fetch(self, cache_key: str, fetch_func: Callable[[], Any]) -> Any:
        """Получает данные из кэша или выполняет запрос"""
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        result = fetch_func()
        if result is not None:
            self._cache[cache_key] = result
        return result
    
    @lru_cache(maxsize=128)
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о пользователе"""
        cache_key = f"user_{username}"
        return self._get_cached_or_fetch(cache_key, 
            lambda: self.api.make_request(f"/users/{quote(username)}"))
    
    def get_user_repos(self, username: str, repos_url: Optional[str] = None) -> Optional[List[Dict]]:
        """Получает список репозиториев пользователя с сортировкой"""
        cache_key = f"repos_{username}"
        
        def fetch_repos():
            url = repos_url or f"/users/{quote(username)}/repos"
            params = {'sort': 'updated', 'per_page': 100, 'direction': 'desc'}
            
            repos = self.api.make_request(url, params)
            return sorted(repos, key=lambda x: x.get('pushed_at', ''), reverse=True) if repos else None
        
        return self._get_cached_or_fetch(cache_key, fetch_repos)
    
    def get_user_events(self, username: str, months: int = 12) -> Optional[List[Dict]]:
        """Получает события пользователя за указанное количество месяцев"""
        cache_key = f"events_{username}_{months}"
        
        def fetch_events():
            since_date = (datetime.now() - timedelta(days=30 * months)).isoformat()
            params = {'per_page': 100, 'since': since_date}
            return self.api.make_request(f"/users/{quote(username)}/events", params)
        
        return self._get_cached_or_fetch(cache_key, fetch_events)
    
    def get_readme_content(self, username: str, repo_name: str) -> str:
        """Получает содержимое README файла с поддержкой разных форматов"""
        cache_key = f"readme_{username}_{repo_name}"
        
        def fetch_readme():
            for readme_file in self.README_FILES:
                url = f"/repos/{quote(username)}/{quote(repo_name)}/contents/{readme_file}"
                readme_data = self.api.make_request(url)
                
                if readme_data and 'content' in readme_data:
                    try:
                        content = base64.b64decode(readme_data['content']).decode('utf-8')
                        return self._clean_readme_content(content)
                    except (base64.binascii.Error, UnicodeDecodeError):
                        continue
            
            return None
        
        result = self._get_cached_or_fetch(cache_key, fetch_readme)
        return result if result else "README файл не найден или не может быть прочитан"
    
    def _clean_readme_content(self, content: str) -> str:
        """Очищает содержимое README от лишней разметки"""
        # Удаляем HTML теги
        content = re.sub(r'<[^>]+>', '', content)
        # Удаляем Markdown ссылки
        content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)
        # Удаляем код блоки
        content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
        # Удаляем лишние пробелы и переносы
        content = ' '.join(content.split())
        return content.strip()
    
    def _calculate_repo_score(self, repo: Dict[str, Any], username: str) -> int:
        """Вычисляет оценку репозитория"""
        score = 0
        
        # Приоритет: репозиторий с именем пользователя
        if repo['name'].lower() == username.lower():
            score += 100
        
        # Наличие README
        if repo.get('readme', False) or repo['has_wiki']:
            score += 50
        
        # Описание репозитория
        if repo.get('description'):
            score += 30
        
        # Активность (последний push)
        if repo.get('pushed_at'):
            try:
                push_date = datetime.fromisoformat(repo['pushed_at'].replace('Z', '+00:00'))
                days_since_push = (datetime.now(push_date.tzinfo) - push_date).days
                if days_since_push < 30:
                    score += 40 - min(days_since_push, 40)
            except (ValueError, TypeError):
                pass
        
        # Количество звезд и форков
        score += min(repo.get('stargazers_count', 0) * 2, 50)
        score += min(repo.get('forks_count', 0), 25)
        
        # Размер репозитория (показатель активности)
        score += min(repo.get('size', 0) // 1000, 20)
        
        return score
    
    def find_best_repo(self, repos: List[Dict], username: str) -> Optional[Dict[str, Any]]:
        """Находит наиболее релевантный репозиторий с улучшенной системой оценки"""
        if not repos:
            return None
        
        scored_repos = [(self._calculate_repo_score(repo, username), repo) for repo in repos]
        scored_repos.sort(key=lambda x: x[0], reverse=True)
        
        return scored_repos[0][1] if scored_repos else repos[0]
    
    def analyze_activity(self, events: List[Dict]) -> Dict[str, Any]:
        """Анализирует активность пользователя с дополнительной статистикой"""
        if not events:
            return self._get_empty_activity_data()
        
        monthly_activity = defaultdict(int)
        activity_by_type = defaultdict(int)
        repo_activity = defaultdict(int)
        last_activity = None
        first_activity = None
        
        for event in events:
            try:
                event_date = datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))
                month_key = event_date.strftime('%Y-%m')
                monthly_activity[month_key] += 1
                
                event_type = event['type']
                activity_by_type[event_type] += 1
                
                # Отслеживаем активность по репозиториям
                repo_name = event['repo']['name'] if event.get('repo') else 'unknown'
                repo_activity[repo_name] += 1
                
                if last_activity is None or event_date > last_activity:
                    last_activity = event_date
                if first_activity is None or event_date < first_activity:
                    first_activity = event_date
                    
            except (KeyError, ValueError):
                continue
        
        total_events = len(events)
        activity_period = (last_activity - first_activity).days + 1 if first_activity and last_activity else 0
        daily_avg = total_events / activity_period if activity_period > 0 else 0
        
        return {
            'total_events': total_events,
            'monthly_activity': dict(monthly_activity),
            'activity_by_type': dict(activity_by_type),
            'repo_activity': dict(repo_activity),
            'last_activity': last_activity,
            'first_activity': first_activity,
            'activity_period_days': activity_period,
            'daily_avg_events': daily_avg
        }
    
    def _get_empty_activity_data(self) -> Dict[str, Any]:
        """Возвращает пустые данные об активности"""
        return {
            'total_events': 0,
            'monthly_activity': {},
            'activity_by_type': {},
            'repo_activity': {},
            'last_activity': None,
            'first_activity': None,
            'activity_period_days': 0,
            'daily_avg_events': 0
        }
    
    def get_activity_summary(self, activity_data: Dict) -> str:
        """Форматирует сводку активности с дополнительной информацией"""
        if activity_data['total_events'] == 0:
            return "❌ Нет активности за указанный период"
        
        summary = []
        summary.append(f"📊 Всего событий: {activity_data['total_events']:,}")
        
        if activity_data['activity_period_days'] > 0:
            summary.append(f"📅 Период активности: {activity_data['activity_period_days']} дней")
            summary.append(f"📈 Средняя активность: {activity_data['daily_avg_events']:.1f} событий/день")
        
        # Активность по месяцам
        if activity_data['monthly_activity']:
            summary.append("\n📅 Активность по месяцам:")
            for month, count in sorted(activity_data['monthly_activity'].items(), reverse=True)[:6]:
                year, month_num = month.split('-')
                month_name = calendar.month_name[int(month_num)]
                summary.append(f"   • {month_name} {year}: {count} событий")
        
        # Активность по типам
        if activity_data['activity_by_type']:
            summary.append("\n🎯 Типы активности:")
            for activity_type, count in sorted(activity_data['activity_by_type'].items(), 
                                             key=lambda x: x[1], reverse=True)[:5]:
                readable_type = self.EVENT_TYPE_MAPPING.get(activity_type, activity_type.replace('Event', ''))
                summary.append(f"   • {readable_type}: {count}")
        
        # Временные метки
        if activity_data['first_activity']:
            first_active = activity_data['first_activity'].strftime('%d.%m.%Y')
            summary.append(f"\n⏰ Первая активность: {first_active}")
        
        if activity_data['last_activity']:
            last_active = activity_data['last_activity'].strftime('%d.%m.%Y %H:%M')
            summary.append(f"⏰ Последняя активность: {last_active}")
        
        return "\n".join(summary)
    
    def get_user_repo_info(self, username: str) -> Tuple[Optional[Dict], str, Optional[str], Optional[Dict]]:
        """
        Получает информацию о репозитории пользователя, README и активность
        с улучшенной обработкой ошибок
        """
        try:
            # Получаем информацию о пользователе
            user_data = self.get_user_info(username)
            if not user_data:
                return None, "Пользователь не найден или аккаунт приватный", None, None
            
            # Получаем список репозиториев
            repos_data = self.get_user_repos(username, user_data.get('repos_url'))
            if not repos_data:
                return user_data, "У пользователя нет публичных репозиториев", None, None
            
            # Находим лучший репозиторий
            personal_repo = self.find_best_repo(repos_data, username)
            if not personal_repo:
                return user_data, "Не удалось найти подходящий репозиторий для анализа", None, None
            
            # Получаем README
            readme_content = self.get_readme_content(username, personal_repo['name'])
            
            # Получаем и анализируем активность
            events = self.get_user_events(username, months=6)
            activity_data = self.analyze_activity(events) if events else None
            
            return user_data, readme_content, personal_repo['name'], activity_data
            
        except Exception as e:
            logger.error(f"Ошибка при обработке пользователя {username}: {e}")
            return None, f"Ошибка обработки: {str(e)}", None, None


def format_date(github_date: Optional[str]) -> str:
    """Форматирует дату из GitHub в читаемый вид"""
    if not github_date:
        return "Неизвестно"
    
    try:
        date_obj = datetime.fromisoformat(github_date.replace('Z', '+00:00'))
        now = datetime.now(date_obj.tzinfo)
        delta = now - date_obj
        
        if delta.days == 0:
            hours = delta.seconds // 3600
            if hours > 0:
                return f"{hours} часов назад"
            minutes = delta.seconds // 60
            return f"{minutes} минут назад" if minutes > 0 else "Только что"
        elif delta.days == 1:
            return "Вчера"
        elif delta.days < 7:
            return f"{delta.days} дней назад"
        elif delta.days < 30:
            weeks = delta.days // 7
            return f"{weeks} недель назад"
        elif delta.days < 365:
            months = delta.days // 30
            return f"{months} месяцев назад"
        else:
            years = delta.days // 365
            return f"{years} лет назад"
            
    except (ValueError, TypeError):
        return "Неизвестно"


def format_user_info(user_data: Dict[str, Any], repo_name: str, 
                    activity_data: Optional[Dict] = None) -> str:
    """Форматирует информацию о пользователе с улучшенным представлением"""
    name = user_data.get('name', user_data.get('login', 'Пользователь'))
    bio = user_data.get('bio', 'Не указана') or 'Не указана'
    location = user_data.get('location', 'Не указано') or 'Не указано'
    
    info_lines = [
        "=" * 70,
        f"🎉 Приветствуем, {name}!",
        f"📝 Биография: {bio}",
        f"📍 Местоположение: {location}",
        f"📅 Присоединился: {format_date(user_data.get('created_at'))}",
        f"👥 Подписчики: {user_data.get('followers', 0):,}",
        f"📈 Подписки: {user_data.get('following', 0):,}",
        f"📊 Публичные репозитории: {user_data.get('public_repos', 0):,}",
    ]
    
    # Дополнительная информация
    additional_info = []
    if user_data.get('company'):
        additional_info.append(f"🏢 Компания: {user_data['company']}")
    if user_data.get('blog'):
        additional_info.append(f"🌐 Блог/сайт: {user_data['blog']}")
    if user_data.get('twitter_username'):
        additional_info.append(f"🐦 Twitter: @{user_data['twitter_username']}")
    
    if additional_info:
        info_lines.extend(additional_info)
    
    info_lines.extend([
        f"🔗 Профиль: {user_data['html_url']}",
        f"📂 Лучший репозиторий: {repo_name}",
    ])
    
    # Информация об активности
    if activity_data and activity_data['total_events'] > 0:
        info_lines.append(f"📈 Активность (6 мес.): {activity_data['total_events']:,} событий")
    
    info_lines.append("=" * 70)
    return "\n".join(info_lines)


def format_readme_preview(readme_content: str, max_length: int = 400) -> str:
    """Форматирует предпросмотр README с улучшенной обработкой"""
    if readme_content.startswith("README файл не найден"):
        return "❌ README файл не найден или не может быть прочитан"
    
    # Очистка и обрезка
    cleaned_content = ' '.join(readme_content.split())
    
    if len(cleaned_content) > max_length:
        # Обрезаем до последнего полного предложения
        truncated = cleaned_content[:max_length]
        if '.' in truncated:
            truncated = truncated.rsplit('.', 1)[0] + '.'
        elif ' ' in truncated:
            truncated = truncated.rsplit(' ', 1)[0]
        
        return (f"{truncated}...\n"
                f"... (показано {len(truncated)} из {len(cleaned_content)} символов)")
    
    return cleaned_content


def process_user(username: str, processor: GitHubUserProcessor) -> bool:
    """
    Обрабатывает запрос для одного пользователя
    Возвращает True если обработка прошла успешно
    """
    logger.info(f"Ищем пользователя {username} на GitHub...")
    
    start_time = time.time()
    user_data, readme_content, repo_name, activity_data = processor.get_user_repo_info(username)
    processing_time = time.time() - start_time
    
    if user_data is None:
        print(f"❌ {readme_content}")
        return False
    
    # Выводим информацию о пользователе
    print(format_user_info(user_data, repo_name, activity_data))
    
    # Выводим анализ активности
    if activity_data:
        print("\n📊 Анализ активности за последние 6 месяцев:")
        print("-" * 50)
        print(processor.get_activity_summary(activity_data))
    
    # Выводим содержимое README
    print("\n📖 Содержимое README файла:")
    print("-" * 40)
    print(format_readme_preview(readme_content))
    
    print(f"\n⏱️ Запрос обработан за {processing_time:.2f} секунд")
    print("=" * 70)
    print("✨ Приятного кодирования!")
    return True


def validate_username(username: str) -> bool:
    """Проверяет валидность имени пользователя GitHub"""
    if not username:
        return False
    
    # GitHub username validation pattern
    pattern = r'^[a-zA-Z\d](?:[a-zA-Z\d]|-(?=[a-zA-Z\d])){0,38}$'
    return re.match(pattern, username) is not None


def main():
    """Основная функция программы с улучшенным интерфейсом"""
    print("👋 Добро пожаловать в GitHub приветственную программу!")
    print("=" * 70)
    print("📊 Теперь с расширенным анализом активности!")
    print("💡 Для выхода введите 'exit', 'quit' или 'выход'")
    print("💡 Для сброса кэша введите 'clear' или 'сброс'")
    print("=" * 70)
    
    # Опционально: можно добавить поддержку GitHub Token для увеличения лимитов
    github_token = None  # os.environ.get('GITHUB_TOKEN')
    processor = GitHubUserProcessor(github_token)
    processed_users = set()
    
    while True:
        try:
            username = input("\n🎯 Введите имя пользователя GitHub: ").strip()
            
            # Проверяем команды выхода
            if username.lower() in ['exit', 'quit', 'выход']:
                print("👋 До свидания!")
                break
            
            # Команда очистки кэша
            if username.lower() in ['clear', 'сброс', 'reset']:
                processor.clear_cache()
                print("✅ Кэш очищен!")
                continue
                
            if not username:
                print("❌ Имя пользователя не может быть пустым!")
                continue
            
            # Валидация имени пользователя
            if not validate_username(username):
                print("❌ Неверный формат имени пользователя GitHub!")
                continue
            
            # Проверяем, не обрабатывали ли уже этого пользователя
            username_lower = username.lower()
            if username_lower in processed_users:
                if input("⚠️ Этот пользователь уже был обработан. Повторить? (y/N): ").lower() != 'y':
                    continue
                # Очищаем кэш для этого пользователя
                keys_to_remove = [k for k in processor._cache.keys() 
                                if k.startswith(f"user_{username}") or k.startswith(f"repos_{username}")]
                for key in keys_to_remove:
                    del processor._cache[key]
            
            # Обрабатываем пользователя
            if process_user(username, processor):
                processed_users.add(username_lower)
                
        except KeyboardInterrupt:
            print("\n\n👋 Программа прервана пользователем. До свидания!")
            break
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            print("❌ Произошла ошибка. Пожалуйста, попробуйте еще раз.")


if __name__ == "__main__":
    main()