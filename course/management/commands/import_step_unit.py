import re
import os
from django.core.management.base import BaseCommand
from course.models import LearningUnit, Step, StepQuestion, StepChoice


class Command(BaseCommand):
    help = 'Импорт пошаговой единицы из текстового файла в базу данных'

    def add_arguments(self, parser):
        parser.add_argument(
            'filepath',
            type=str,
            help='Путь к текстовому файлу с пошаговой единицей',
        )

    def handle(self, *args, **options):
        filepath = options['filepath']
        if not os.path.exists(filepath):
            self.stderr.write(self.style.ERROR(f'Файл не найден: {filepath}'))
            return

        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()

        # Извлекаем заголовок единицы из первой строки
        lines = text.split('\n')
        unit_title = 'Пошаговая единица'
        for line in lines:
            line = line.strip()
            if line.startswith('Пошаговая единица:') or line.startswith('Пошаговая единица'):
                unit_title = line.replace('Пошаговая единица:', '').replace('Пошаговая единица', '').strip()
                break

        # Создаём LearningUnit
        learning_unit = LearningUnit.objects.create(
            title=unit_title or 'Пошаговая единица',
            content_type='step_by_step',
        )
        self.stdout.write(self.style.SUCCESS(f'Создана пошаговая единица: {learning_unit.title} (ID={learning_unit.pk})'))

        # Разбиваем на шаги по паттерну "ШАГ N."
        step_pattern = re.compile(r'ШАГ\s+(\d+)\.\s*(.+?)(?=\nШАГ\s+\d+\.|\Z)', re.DOTALL)
        # Найдём начало первого шага
        first_step_match = re.search(r'ШАГ\s+1\.', text)
        if not first_step_match:
            self.stderr.write(self.style.ERROR('Не найден ШАГ 1 в файле'))
            return

        steps_text = text[first_step_match.start():]
        step_matches = list(re.finditer(r'ШАГ\s+(\d+)\.\s*(.+?)(?=\nШАГ\s+\d+\.|\Z)', steps_text, re.DOTALL))

        self.stdout.write(f'Найдено шагов: {len(step_matches)}')

        for match in step_matches:
            step_num = int(match.group(1))
            step_block = match.group(0)
            title_remainder = match.group(2).strip()
            # Первая строка блока после "ШАГ N." — заголовок
            block_lines = match.group(2).strip().split('\n', 1)
            step_title = block_lines[0].strip()

            # Всё после заголовка до "Вопрос:" — контент шага
            if len(block_lines) > 1:
                remainder = block_lines[1].strip()
            else:
                remainder = ''

            # Ищем вопрос и варианты
            question_match = re.search(r'Вопрос:\s*(.+?)(?=\n[A-Z]\))', remainder, re.DOTALL)
            if question_match:
                question_text = question_match.group(1).strip()
                content_before_question = remainder[:question_match.start()].strip()
            else:
                question_text = ''
                content_before_question = remainder.strip()

            # Создаём шаг
            step = Step.objects.create(
                learning_unit=learning_unit,
                title=step_title,
                content=content_before_question,
                order=step_num,
            )
            self.stdout.write(f'  Шаг {step_num}: {step_title}')

            # Создаём вопрос если есть
            if question_text:
                question = StepQuestion.objects.create(
                    step=step,
                    text=question_text,
                    order=1,
                )

                # Ищем варианты ответов
                choice_pattern = re.compile(r'([A-Z])\)\s*(.+?)(?=\n[A-Z]\)|\nПравильный ответ:|\Z)', re.DOTALL)
                choices_found = list(choice_pattern.finditer(remainder))

                # Ищем правильный ответ
                correct_match = re.search(r'Правильный ответ:\s*([A-Z])', remainder)
                correct_letter = correct_match.group(1) if correct_match else None

                for choice_match in choices_found:
                    letter = choice_match.group(1)
                    choice_text = choice_match.group(2).strip()
                    is_correct = (letter == correct_letter)
                    StepChoice.objects.create(
                        question=question,
                        text=choice_text,
                        is_correct=is_correct,
                    )
                    check = '✓' if is_correct else ' '
                    self.stdout.write(f'    [{check}] {letter}) {choice_text[:60]}...' if len(choice_text) > 60 else f'    [{check}] {letter}) {choice_text}')

        self.stdout.write(self.style.SUCCESS(f'Импорт завершён. Создана единица ID={learning_unit.pk} с {len(step_matches)} шагами.'))