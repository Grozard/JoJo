# GitHub User Info Fetcher

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()
[![Group](https://img.shields.io/badge/Группа-21ИС-important)]()
[![Command](https://img.shields.io/badge/Команда-003-success)]()

Консольная утилита на Python для получения информации о профиле GitHub и содержимого README-файлов через GitHub API.

**Разработчик:** Грозный Дио (Grozio) 😊  
**Локация:** Egypt  
**Биография:** NAAANI
**Команда:** 003
**Группа:** 21ИС

## ✨ Функциональность


*   **Получение данных профиля:** Максим, None, Egypt, https://github.com/Grozard
*   **Поиск репозиториев:** https://github.com/Grozard/JoJo
*   **Обработка ошибок:** Если пользователь с таким user_name не найден то программа напишет: 
[🔍 Ищем пользователя <USER> на GitHub...]
[👋 Здравствуйте, неизвестный пользователь!]


Если пользователь найден но у него нету репозитория то программа напишет:
 [Ищем пользователя <USER> на GitHub...]
[❌ У пользователя нет репозиториев]


Если пользователь найден и у него есть репозиторий то программа наипшет:
[🎉 Приветствуем, <USER>!]
[📝 Биография: None]
[📍 Местоположение: None]
[🔗 Профиль: https://github.com/<USER>]
[📂 Репозиторий: My-project]
