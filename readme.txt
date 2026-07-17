================================================================================
                        ПРОЕКТ: MSUDLE (msudle)
================================================================================

1. ОБЩАЯ ИНФОРМАЦИЯ
--------------------------------------------------------------------------------
Msudle — образовательная веб-платформа (LMS, аналог Moodle) на Django 4.2.18.
Проект создан для управления учебным процессом: структура вуза, курсы, студенты.
Язык интерфейса: русский (ru), часовой пояс: Europe/Moscow.
Git-репозиторий: https://github.com/stanislaumich/django.git

Стек: Python 3 + Django 4.2 + SQLite + Bootstrap 5 (локально) + Bootstrap Icons.

2. СТРУКТУРА ПРОЕКТА
--------------------------------------------------------------------------------
msudle/                         # Корень Django-проекта
├── manage.py                   # Django management script
├── db.sqlite3                  # База данных SQLite (уже есть данные)
├── favicon.ico                 # Иконка сайта
├── prompt.txt                  # Задачи
├── readme.txt                  # Этот файл
├── msudle/                     # Конфигурация проекта
│   ├── settings.py
│   ├── urls.py                 # admin/ + main/ + students/ + accounts/
│   ├── wsgi.py
│   └── asgi.py
├── main/                       # Лендинг + Dashboard (личный кабинет)
├── structure/                  # Оргструктура вуза (University→Faculty→Department)
│   └── migrations/  (0001-0005)
├── subject/                    # Дисциплины (Subject, FK→Department)
├── students/                   # Студенты + StudentGroup + аутентификация
│   └── migrations/  (0001-0011)
├── course/                     # Курсы обучения
│   └── migrations/  (0001-0007)
├── umo/                        # Модель Shifr (шифры направлений/специальностей)
├── accounts/                   # Профили, API генерации логина, автокомплит для User
├── templates/
│   ├── base.html               # Базовый шаблон (navbar, тёмная тема, логин/ФИО/роль)
│   ├── main/
│   │   ├── index.html          # Главная страница (лендинг)
│   │   └── dashboard.html      # Личный кабинет — плашки курсов (3 колонки)
│   └── admin/
│       └── base_site.html      # Кастомизация заголовков админки
└── static/                     # Bootstrap 5 + Icons локально, main.css

3. ПРИЛОЖЕНИЯ
--------------------------------------------------------------------------------

3.1. main — лендинг и личный кабинет.
    - index() — лендинг для гостей и студентов; редирект на /courses/ для сотрудников.
    - dashboard() (/courses/) — личный кабинет сотрудника/админа:
        - Плашки курсов в 3 колонки (Bootstrap grid: col-lg-4 col-md-6 col-12).
        - На карточке: полное название курса, полное название кафедры,
          уровень доступа (текстом), две кнопки: «Просмотр» (синяя) и
          «Редактирование» (красная).
        - Права собираются из CourseUserPermission (персональные) и
          CourseGroupPermission (через группы пользователя).
        - Курсы сортируются по уровню прав (полный доступ → просмотр).
    - verbose_name в apps.py: 'ГЛАВНАЯ'.

3.2. structure — University → Faculty → Department.
    - Faculty.dean (FK→User) — декан. Department.head (FK→User) — зав. кафедрой.
    - При назначении/смене декана/зав. кафедрой — автоматическое управление
      группами «Декан»/«Заведующий кафедрой» (auth.Group).
    - __str__() → full_name. identifier: nullable.
    - verbose_name в apps.py: 'ОРГАНИЗАЦИЯ'.
    - Миграции: 0001-0005.

3.3. subject — дисциплины (Subject, FK→Department). __str__() → full_name.
    - verbose_name в apps.py: 'ПРЕДМЕТЫ'.

3.4. students — студенты + аутентификация.
    Модели:
      - StudentGroup (Группа студентов):
          group_number (CharField 50), subgroup_number (PositiveSmallIntegerField, null)
          shifr (FK→umo.Shifr, SET_NULL, null, blank),
          enrollment_year, study_duration_years, study_duration_months,
          faculty (FK→structure.Faculty), education_form (daytime/correspondence)
          unique_together: (group_number, subgroup_number)
      - Student (Студент):
          fio, group (FK→StudentGroup, null, blank), login (unique),
          password (хэш), last_login
          Свойства: is_authenticated, is_active, get_username(), get_full_name()
    Аутентификация: StudentBackend (по login) + EmailOrUsernameBackend (по username/email).
    После логина: сотрудники/админы → /courses/, студенты → /.
    Админка: StudentGroupAdmin (list_display: group_number, subgroup_number, shifr,
             enrollment_year, faculty, education_form), StudentAdmin.
    verbose_name в apps.py: 'СТУДЕНТЫ'.
    Миграции: 0001-0011.

3.5. course — курсы обучения.
    Модели: Course, CourseUserPermission, CourseGroupPermission,
            CourseSection, CourseTopic, LearningUnit, CourseGroupStudent.
    CourseGroupStudent.group: FK→StudentGroup (вместо group_number).
    Права: edit / create_delete / view / full_access (пользователям и группам).
    При создании курса автоматически назначаются права:
      - создателю — полный доступ (full_access)
      - декану факультета — просмотр (view)
      - заведующему кафедрой — просмотр (view)
      - группе «УМО» — просмотр (view)
      - группе «Ректорат» — просмотр (view)
      - добавляются разделы по умолчанию (6 разделов)
    verbose_name в apps.py: 'КУРСЫ'.
    Миграции: 0001-0007.

3.6. umo — шифры направлений/специальностей.
    Модель Shifr:
        code (CharField 20) — шифр, напр. 6-05-0612-01, 1-40-01-01
        name (CharField 300, null, blank) — название шифра
        qualification (CharField 300, null, blank) — квалификация
    StudentGroup.shifr — FK → Shifr (SET_NULL).
    Админка: ShifrAdmin (list_display: code, name, qualification; search: code, name).
    verbose_name в apps.py: 'СПЕЦИАЛЬНОСТИ'.
    Миграции: 0001-0002.

3.7. accounts — API генерации логина + JS для админки User.
    POST /accounts/generate-login/ — генерирует username из ФИО (транслит + 3 цифры).
    auto_login.js — автозаполнение #id_username при вводе ФИО.
    CustomUserAdmin — кастомный autocomplete с «Фамилия Имя (username)».
    verbose_name в apps.py: 'ПОЛЬЗОВАТЕЛИ'.

4. СИСТЕМА АУТЕНТИФИКАЦИИ
--------------------------------------------------------------------------------
 Два независимых бэкенда: StudentBackend + EmailOrUsernameBackend.
 Отображение в navbar:
  - Студент: ФИО, группа/подгруппа
  - User: имя/username, роль (Администратор/Сотрудник), группы
 Маршрутизация после логина:
  - Сотрудники/админы → /courses/ (dashboard с курсами)
  - Студенты → / (лендинг)
 Главная страница (/) для уже авторизованных сотрудников: редирект на /courses/.

5. НАСТРОЙКИ (settings.py)
--------------------------------------------------------------------------------
- DEBUG: True, LANGUAGE_CODE: 'ru', TIME_ZONE: 'Europe/Moscow'
- DATABASE: SQLite
- INSTALLED_APPS: полные пути до AppConfig (course.apps.CourseConfig, ...)
  для корректной работы verbose_name в админке
- AUTHENTICATION_BACKENDS: StudentBackend, EmailOrUsernameBackend
- STATIC_URL: 'static/', STATICFILES_DIRS: [BASE_DIR / 'static']
- MEDIA_URL: '/media/', MEDIA_ROOT: BASE_DIR / 'data'

6. АДМИНКА
--------------------------------------------------------------------------------
- URL: /admin/ (нужен superuser)
- Заголовки: site_header='msudle', site_title='msudle',
  index_title='Управление платформой' (заданы в urls.py)
- Группы моделей отображаются с русскими названиями:
  КУРСЫ, СТУДЕНТЫ, ПРЕДМЕТЫ, ОРГАНИЗАЦИЯ, СПЕЦИАЛЬНОСТИ, ПОЛЬЗОВАТЕЛИ, ГЛАВНАЯ
- При создании User в админке логин (username) генерируется автоматически из ФИО

7. ИНТЕРФЕЙС (ТЁМНАЯ ТЕМА)
--------------------------------------------------------------------------------
- Реализована через CSS-переменные в static/css/main.css
- Переключение: кнопка с иконкой луны/солнца в navbar (справа)
- Выбор сохраняется в localStorage (ключ 'msudle-theme')
- Тёмная тема: фон #1a1d23, карточки #212529, текст #e9ecef
- Все переходы плавные (0.3s transition)

8. КЛЮЧЕВЫЕ ТОЧКИ
--------------------------------------------------------------------------------
- Запуск: python manage.py runserver
- Админка: /admin/ (нужен superuser)
- Логин: кнопка «Войти» в navbar → форма (username/email/логин_студента + пароль)
- Личный кабинет: /courses/ — плашки курсов с правами (3 колонки)
- Статические файлы локально в static/; шаблоны наследуются от base.html
- StudentGroup.shifr → FK → umo.Shifr (нормализованная связь «группа — шифр»)
- Student.group → FK → StudentGroup (nullable)
- CourseGroupStudent.group → FK → StudentGroup (вместо CharField)
- Декан/зав. кафедрой управляются через группы «Декан»/«Заведующий кафедрой»
- При создании User в админке логин (username) генерируется автоматически из ФИО
- При создании курса автоматически назначаются права и разделы по умолчанию