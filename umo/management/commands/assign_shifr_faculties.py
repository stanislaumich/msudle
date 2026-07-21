"""Management command: авто-назначение факультетов для шифров по ключевым словам в названии."""
from django.core.management.base import BaseCommand
from umo.models import Shifr
from structure.models import Faculty
import re


class Command(BaseCommand):
    help = 'Assign faculty to shifrs based on name keywords.'

    def handle(self, *args, **options):
        faculties = {f.id: f for f in Faculty.objects.all()}
        shifrs = Shifr.objects.all()
        updated = 0
        skipped = 0

        for s in shifrs:
            fid = self._match_faculty(s)
            if fid is not None and s.faculty_id != fid:
                s.faculty_id = fid
                s.save(update_fields=['faculty'])
                updated += 1
                self.stdout.write(f'  {s.code} → {faculties.get(fid, "?").full_name}')
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Назначено: {updated}, пропущено: {skipped}.'
        ))

    def _match_faculty(self, shifr):
        name = (shifr.name or '').lower()
        code = (shifr.code or '')

        # 1. Факультет иностранных языков (id=1)
        if self._any_word(name, [
            'иностранн', 'английск', 'немецк', 'французск', 'испанск',
            'роман', 'герман', 'межкультурн', 'лингвист', 'перевод',
        ]):
            return 1
        # Восточная филология — тоже языки
        if 'восточн' in name and 'филолог' in name:
            return 1
        if 'современн' in name and 'иностран' in name:
            return 1

        # 2. Историко-филологический факультет (id=2)
        if self._any_word(name, [
            'истори', 'философ', 'социолог', 'политолог', 'регионовед',
            'востоковед', 'религиовед', 'теолог', 'архив', 'библиотеч',
            'музейн', 'журналист', 'медиакоммуник', 'информац и коммуникац',
            'делопроизводств', 'документовед',
        ]):
            return 2
        # Филология (кроме восточной и романо-германской — те к языкам)
        if 'филолог' in name:
            if 'восточн' not in name and 'роман' not in name and 'герман' not in name and 'славян' not in name:
                return 2
        if 'литератур' in name and 'языкозна' not in name:
            return 2
        if 'славянск' in name:
            return 2
        if 'белорусск' in name and 'филолог' in name:
            return 2
        if 'русск' in name and 'филолог' in name:
            return 2
        if 'классическ' in name and 'филолог' in name:
            return 2
        if 'литературн' in name and 'работ' in name:
            return 2
        if 'языкозна' in name:
            return 2
        if 'панславянск' in name:
            return 2

        # 3. Факультет педагогики и психологии детства (id=3)
        if self._any_word(name, [
            'дошкольн', 'психолог', 'инклюзив',
        ]):
            return 3
        if 'социальн' in name and ('педагог' in name or 'психолог' in name or 'работ' in name):
            return 3
        if 'специальн' in name and ('образован' in name or 'дошкольн' in name):
            return 3

        # 4. Факультет начального и музыкального образования (id=4)
        if self._any_word(name, [
            'начальн', 'музыкальн', 'хореограф', 'вокал', 'дириж',
            'композиц', 'инструмент', 'музыковед', 'декоратив',
            'дизайн', 'художествен', 'искусств', 'актер', 'режисс',
            'аудиовизуальн', 'сценограф', 'живопис', 'скульптур',
            'график', 'народн творчеств', 'традицион культ',
            'изобразительн', 'экран', 'театральн', 'монументальн',
            'народн творчеств', 'творчество',
        ]):
            if 'искусствен' in name and 'интеллект' in name:
                return 5  # Искусственный интеллект → матфак
            return 4
        if 'технологическ' in name and 'образован' in name:
            # Технологическое образование — в начальное/музыкальное (педагогический блок)
            return 4

        # 5. Факультет математики и естествознания (id=5)
        if self._any_word(name, [
            'математи', 'физик', 'хими', 'биолог', 'географ', 'геолог',
            'эколог', 'информатик', 'программ', 'компьютер',
            'микробиолог', 'биохим', 'биотех', 'гидрометео',
            'радиофиз', 'ядерн', 'механ', 'актуар',
            'кибер', 'веб-програм', 'интернет-технолог',
            'искусствен инт', 'электрон маркет', 'робот',
            'картограф', 'космо',
        ]):
            return 5
        if 'информацион' in name and ('систем' in name or 'технолог' in name or 'ресурс' in name):
            return 5
        if 'прикладн' in name and ('информат' in name or 'математик' in name):
            return 5
        if 'математическ' in name and 'образован' in name:
            return 5
        if 'природовед' in name:
            return 5
        if 'естественнонауч' in name:
            return 5
        if 'компьютерн' in name and ('физик' in name or 'математик' in name or 'безопас' in name or 'инженер' in name):
            return 5
        if 'программн' in name and 'инженер' in name:
            return 5
        if 'систем' in name and 'управлен' in name and 'информац' in name:
            return 5

        # 6. Факультет физического воспитания (id=6)
        if self._any_word(name, [
            'физическ культур', 'физическ воспитан', 'спорт',
            'спортивн', 'туристск', 'туризм и гост',
            'экологическ туризм',
        ]):
            return 6
        if 'физическ' in name and ('культур' in name or 'воспитан' in name):
            return 6

        # 7. Факультет экономики и права (id=7)
        if self._any_word(name, [
            'экономи', 'финанс', 'бухгалтер', 'менеджмент', 'маркетинг',
            'логистик', 'бизнес', 'правов', 'юрис', 'налогооблож',
            'кредит', 'аудит', 'реклам', 'государствен управлен',
            'государствен и экономик', 'управлен персонал',
            'управлен информацион ресурс', 'управлен недвижим',
            'организац производств', 'энергетическ менеджмент',
            'коммунальн хозяйств', 'бытов', 'ресторан', 'гостиничн',
            'туризм', 'экспедиторск', 'транспортн логист',
        ]):
            return 7
        if 'управлен' in name:
            return 7
        if 'производств' in name and 'организац' in name:
            return 7
        if 'охрана обществен' in name:
            return 7
        if 'судебн' in name and ('эксперт' in name or 'деятельн' in name):
            return 7
        if 'прокурорск' in name:
            return 7
        if 'национальн безопас' in name:
            return 7
        if 'пограничн' in name:
            return 7

        # Не подошло — оставляем без факультета
        return None

    @staticmethod
    def _any_word(text: str, words: list) -> bool:
        for w in words:
            if w in text:
                return True
        return False