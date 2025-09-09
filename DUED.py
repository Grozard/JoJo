import requests
import json
import base64
import webbrowser

def get_user_repo_info(username):
    """
    Получает информацию о репозитории пользователя и README файл
    """
    # URL для получения информации о пользователе
    user_url = f"https://api.github.com/users/{username}"
    
    try:
        # Получаем информацию о пользователе
        user_response = requests.get(user_url)
        
        # Если пользователь не найден (статус 404)
        if user_response.status_code == 404:
            return None, "Пользователь не найден", None
            
        user_response.raise_for_status()
        user_data = user_response.json()
        
        # Получаем список репозиториев пользователя
        repos_url = user_data['repos_url']
        repos_response = requests.get(repos_url)
        repos_response.raise_for_status()
        repos_data = repos_response.json()
        
        # Ищем репозиторий с именем пользователя (обычно это основной репозиторий)
        personal_repo = None
        for repo in repos_data:
            if repo['name'].lower() == username.lower():
                personal_repo = repo
                break
        
        # Если не нашли репозиторий с именем пользователя, берем первый репозиторий
        if not personal_repo and repos_data:
            personal_repo = repos_data[0]
        
        if not personal_repo:
            return None, "У пользователя нет репозиториев", None
        
        # Получаем README файл
        readme_url = f"https://api.github.com/repos/{username}/{personal_repo['name']}/readme"
        readme_response = requests.get(readme_url)
        
        if readme_response.status_code == 200:
            readme_data = readme_response.json()
            # Декодируем содержимое README из base64
            readme_content = base64.b64decode(readme_data['content']).decode('utf-8')
        else:
            readme_content = "README файл не найден"
        
        return user_data, readme_content, personal_repo['name']
        
    except requests.exceptions.RequestException as e:
        return None, f"Ошибка при подключении к GitHub: {e}", None
    except json.JSONDecodeError:
        return None, "Ошибка при обработке данных", None

def offer_registration(username):
    """
    Предлагает пользователю зарегистрироваться на GitHub
    """
    print(f"\n🤔 Пользователь '{username}' не найден на GitHub!")
    print("=" * 50)
    print("Возможно, вы:")
    print("1. Ошиблись в написании имени")
    print("2. Еще не зарегистрированы на GitHub")
    print("3. Имеете приватный аккаунт")
    print("=" * 50)
    
    choice = input("Хотите зарегистрироваться на GitHub? (y/n): ").strip().lower()
    
    if choice in ['y', 'yes', 'да', 'д']:
        print("\n🎯 Открываю страницу регистрации GitHub...")
        print("🔗 https://github.com/signup")
        webbrowser.open("https://github.com/signup")
        print("\n✅ После регистрации вы сможете:")
        print("   - Создавать репозитории")
        print("   - Участвовать в open-source проектах")
        print("   - Хранить свой код в облаке")
        print("   - Сотрудничать с другими разработчиками")
    else:
        print("\n👌 Хорошо! Проверьте правильность введенного имени.")
        print("💡 Подсказка: имя пользователя чувствительно к регистру")

def process_user(username):
    """
    Обрабатывает запрос для одного пользователя
    """
    print(f"\n🔍 Ищем пользователя {username} на GitHub...")
    
    # Получаем информацию о пользователе и его README
    user_data, readme_content, repo_name = get_user_repo_info(username)
    
    if user_data is None:
        if readme_content == "Пользователь не найден":
            print(f"👋 Здравствуйте!")
            offer_registration(username)
        else:
            print(f"❌ {readme_content}")
        return
    
    # Выводим приветствие с информацией о пользователе
    print("\n" + "=" * 50)
    print(f"🎉 Приветствуем, {user_data.get('name', username)}!")
    print(f"📝 Биография: {user_data.get('bio', 'Не указана')}")
    print(f"📍 Местоположение: {user_data.get('location', 'Не указано')}")
    print(f"🔗 Профиль: {user_data['html_url']}")
    if repo_name:
        print(f"📂 Репозиторий: {repo_name}")
    print("=" * 50)
    
    # Выводим содержимое README
    if readme_content and readme_content != "README файл не найден":
        print("\n📖 Содержимое README файла:")
        print("-" * 30)
        # Ограничиваем вывод до первых 500 символов
        preview = readme_content[:500] + "..." if len(readme_content) > 500 else readme_content
        print(preview)
        if len(readme_content) > 500:
            print("... (показаны первые 500 символов)")
    
    print("\n" + "=" * 50)
    print("✨ Приятного кодирования!")

def main():
    """
    Основная функция программы
    """
    print("👋 Добро пожаловать в GitHub приветственную программу!")
    print("=" * 50)
    print("Введите 'exit' или 'quit' для выхода из программы")
    print("=" * 50)
    
    while True:
        # Получаем имя пользователя
        username = input("\nВведите имя пользователя GitHub: ").strip()
        
        # Проверяем команды выхода
        if username.lower() in ['exit', 'quit', 'выход']:
            print("👋 До свидания!")
            break
            
        if not username:
            print("❌ Имя пользователя не может быть пустым!")
            continue
        
        # Обрабатываем пользователя
        process_user(username)

if __name__ == "__main__":
    main()