django.jQuery(function($) {
    'use strict';

    var $firstName = $('#id_first_name');
    var $lastName  = $('#id_last_name');
    var $username  = $('#id_username');

    if (!$firstName.length || !$lastName.length || !$username.length) {
        return;
    }

    function updateLogin() {
        var firstName = $firstName.val().trim();
        var lastName  = $lastName.val().trim();
        var fullName  = (lastName + ' ' + firstName).trim();

        if (!fullName) {
            // Не очищаем username, если он уже заполнен
            if (!$username.val()) {
                $username.val('');
            }
            return;
        }

        $.ajax({
            url: '/accounts/generate-login/',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ full_name: fullName }),
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            success: function(data) {
                if (data.success && data.login) {
                    $username.val(data.login);
                }
            },
            error: function(xhr, status, err) {
                console.error('auto_login error:', status, err);
            }
        });
    }

    var timeout;
    $firstName.add($lastName).on('input', function() {
        clearTimeout(timeout);
        timeout = setTimeout(updateLogin, 400);
    });

    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = $.trim(cookies[i]);
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});