from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username='admin', password='secret1234')

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)


class LoginTrackingTests(TestCase):
    def test_successful_login_records_event(self):
        from apps.core.models import LoginEvent
        get_user_model().objects.create_user(username='logger', password='secret1234')
        response = self.client.post(
            reverse('login'),
            {'username': 'logger', 'password': 'secret1234'},
            HTTP_USER_AGENT='TestAgent/1.0',
        )
        self.assertEqual(response.status_code, 302)
        event = LoginEvent.objects.get(user__username='logger')
        self.assertEqual(event.user_agent, 'TestAgent/1.0')
        self.assertTrue(event.ip_address)

    def test_failed_login_records_nothing(self):
        from apps.core.models import LoginEvent
        get_user_model().objects.create_user(username='logger2', password='secret1234')
        self.client.post(reverse('login'), {'username': 'logger2', 'password': 'wrong'})
        self.assertFalse(LoginEvent.objects.filter(user__username='logger2').exists())

    def test_register_records_event(self):
        from apps.core.models import LoginEvent
        self.client.post(reverse('register'), {
            'username': 'newbie', 'first_name': 'New', 'last_name': 'Bie',
            'email': 'newbie@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
        })
        self.assertTrue(LoginEvent.objects.filter(user__username='newbie').exists())

    def test_register_creates_staff_not_superuser(self):
        self.client.post(reverse('register'), {
            'username': 'staffer', 'first_name': 'Sta', 'last_name': 'Ffer',
            'email': 'staffer@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
        })
        user = get_user_model().objects.get(username='staffer')
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_new_staff_can_login_but_not_manage_users(self):
        self.client.post(reverse('register'), {
            'username': 'staffer2', 'first_name': 'Sta', 'last_name': 'Ffer',
            'email': 'staffer2@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
        })
        self.client.logout()
        response = self.client.post(
            reverse('login'), {'username': 'staffer2', 'password': 'StrongPass123!'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse('users:user_list')).status_code, 302)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_login_page_links_to_register(self):
        self.assertContains(self.client.get(reverse('login')), 'Register')

    def test_dashboard_shows_recent_logins(self):
        get_user_model().objects.create_user(username='viewer', password='secret1234')
        self.client.post(reverse('login'), {'username': 'viewer', 'password': 'secret1234'})
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Recent logins')
        self.assertContains(response, 'viewer')

    def test_login_updates_last_login(self):
        user = get_user_model().objects.create_user(username='lastlog', password='secret1234')
        self.assertIsNone(user.last_login)
        self.client.post(reverse('login'), {'username': 'lastlog', 'password': 'secret1234'})
        user.refresh_from_db()
        self.assertIsNotNone(user.last_login)
