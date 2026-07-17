import json
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from .models import Test, Question, Choice


def _is_teacher(user):
    return not hasattr(user, 'fio')


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def api_my_tests(request):
    """GET — список тестов текущего преподавателя. Возвращает [{id, name, subject_name}]."""
    tests = Test.objects.select_related('subject').filter(author=request.user).order_by('-created_at')
    data = [
        {'id': t.id, 'name': t.name, 'subject_name': t.subject.full_name}
        for t in tests
    ]
    return JsonResponse({'tests': data})


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def api_question_list(request, test_id):
    """GET — список вопросов теста с вариантами."""
    test = get_object_or_404(Test, id=test_id)
    questions = test.questions.prefetch_related('choices').all()
    data = []
    for q in questions:
        data.append({
            'id': q.id,
            'text': q.text,
            'question_type': q.question_type,
            'order': q.order,
            'score': q.score,
            'choices': [
                {'id': c.id, 'text': c.text, 'is_correct': c.is_correct}
                for c in q.choices.all()
            ],
        })
    return JsonResponse({'questions': data})


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
@require_POST
def api_question_create(request, test_id):
    """POST — создать вопрос. body: {text, question_type, order, score, choices: [{text, is_correct}]}"""
    test = get_object_or_404(Test, id=test_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный JSON'}, status=400)
    text = data.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'Введите текст вопроса'}, status=400)
    q_type = data.get('question_type', 'single')
    if q_type not in ('single', 'multiple'):
        q_type = 'single'
    order = data.get('order', test.questions.count())
    score = int(data.get('score', 1))
    if score < 1:
        score = 1
    q = Question.objects.create(
        test=test,
        text=text,
        question_type=q_type,
        order=order,
        score=score,
    )
    # Create choices
    choices_data = data.get('choices', [])
    choices = []
    for cdata in choices_data:
        choice = Choice.objects.create(
            question=q,
            text=cdata.get('text', '').strip(),
            is_correct=bool(cdata.get('is_correct', False)),
        )
        choices.append({'id': choice.id, 'text': choice.text, 'is_correct': choice.is_correct})
    return JsonResponse({
        'id': q.id,
        'text': q.text,
        'question_type': q.question_type,
        'order': q.order,
        'score': q.score,
        'choices': choices,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
@require_POST
def api_question_update(request, question_id):
    """POST — обновить вопрос. body: как create, + method=delete для удаления."""
    q = get_object_or_404(Question, id=question_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный JSON'}, status=400)
    if data.get('method') == 'delete':
        q.delete()
        return JsonResponse({'deleted': True})
    text = data.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'Введите текст вопроса'}, status=400)
    q.text = text
    q.question_type = data.get('question_type', q.question_type)
    if q.question_type not in ('single', 'multiple'):
        q.question_type = 'single'
    q.order = data.get('order', q.order)
    score = int(data.get('score', q.score))
    if score < 1:
        score = 1
    q.score = score
    q.save()
    # Recreate choices
    choices_data = data.get('choices', [])
    if choices_data:
        q.choices.all().delete()
        for cdata in choices_data:
            Choice.objects.create(
                question=q,
                text=cdata.get('text', '').strip(),
                is_correct=bool(cdata.get('is_correct', False)),
            )
    choices = [
        {'id': c.id, 'text': c.text, 'is_correct': c.is_correct}
        for c in q.choices.all()
    ]
    return JsonResponse({
        'id': q.id,
        'text': q.text,
        'question_type': q.question_type,
        'order': q.order,
        'score': q.score,
        'choices': choices,
    })