from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class UserCrudTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username='boss', password='secret1234', email='boss@example.com')
        self.staff = User.objects.create_user(username='staff', password='secret1234')
        self.client.force_login(self.admin)

    def test_create_user_hashes_password(self):
        response = self.client.post(reverse('users:user_save_ajax'), {
            'username': 'fresh', 'first_name': 'Fre', 'last_name': 'Sh',
            'email': 'fresh@example.com', 'password': 'StrongPass123!',
            'is_staff': 'false', 'is_active': 'true',
        })
        self.assertEqual(response.status_code, 200)
        user = get_user_model().objects.get(username='fresh')
        self.assertTrue(user.check_password('StrongPass123!'))

    def test_create_requires_password(self):
        response = self.client.post(reverse('users:user_save_ajax'), {
            'username': 'nopass', 'email': '',
        })
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_duplicate_username(self):
        response = self.client.post(reverse('users:user_save_ajax'), {
            'username': 'staff', 'email': '', 'password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 400)

    def test_edit_user(self):
        response = self.client.post(reverse('users:user_save_ajax'), {
            'id': self.staff.id, 'username': 'staff',
            'first_name': 'Sta', 'last_name': 'Ff', 'email': 's@example.com',
            'is_staff': 'false', 'is_active': 'true',
        })
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.first_name, 'Sta')

    def test_delete_user(self):
        target = get_user_model().objects.create_user(username='gone', password='secret1234')
        response = self.client.post(reverse('users:user_delete_ajax', args=[target.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username='gone').exists())

    def test_cannot_delete_self(self):
        response = self.client.post(reverse('users:user_delete_ajax', args=[self.admin.id]))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(get_user_model().objects.filter(username='boss').exists())

    def test_non_superuser_blocked(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 302)

    def test_non_superuser_blocked_from_ajax(self):
        self.client.force_login(self.staff)
        for url in [
            reverse('users:user_list_ajax'),
            reverse('users:user_save_ajax'),
            reverse('users:user_get_ajax', args=[self.admin.id]),
            reverse('users:user_delete_ajax', args=[self.admin.id]),
        ]:
            response = self.client.post(url) if 'save' in url or 'delete' in url else self.client.get(url)
            self.assertIn(response.status_code, (302, 403), url)

    def test_sidebar_users_link_admin_only(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), 'Users')
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Users')

    def test_list_shows_add_button_and_last_login(self):
        response = self.client.get(reverse('users:user_list'))
        self.assertContains(response, 'Add User')
        self.assertContains(response, 'Last login')
