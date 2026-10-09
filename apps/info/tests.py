from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.info.models import Info


class InfoScopingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username='infoboss', password='secret1234', email='b@example.com')
        self.staff = User.objects.create_user(username='infoworker', password='secret1234')
        self.record = Info.objects.create(
            user=self.staff, name='Scoped Person', age=30, address='Somewhere')

    def test_staff_sees_own_record(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse('info:info_list')), 'Scoped Person')

    def test_admin_sees_staff_record(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('info:info_list'))
        self.assertContains(response, 'Scoped Person')
        self.assertContains(response, 'infoworker')

    def test_staff_cannot_open_admin_record(self):
        Info.objects.create(user=self.admin, name='Admin Only', age=40, address='HQ')
        self.client.force_login(self.staff)
        admin_record = Info.objects.get(name='Admin Only')
        response = self.client.get(reverse('info:info_get_ajax', args=[admin_record.id]))
        self.assertEqual(response.status_code, 404)

    def test_admin_edit_keeps_owner(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('info:info_save_ajax'), {
            'id': self.record.id, 'name': 'Scoped Person',
            'age': '31', 'address': 'Somewhere', 'email': '',
        })
        self.assertEqual(response.status_code, 200)
        self.record.refresh_from_db()
        self.assertEqual(self.record.age, 31)
        self.assertEqual(self.record.user, self.staff)

    def test_save_message_renders_as_toast(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('info:info_save_ajax'), {
            'id': self.record.id, 'name': 'Scoped Person',
            'age': '31', 'address': 'Somewhere', 'email': '',
        })
        response = self.client.get(reverse('info:info_list'))
        self.assertContains(response, 'toast-container')
        self.assertContains(response, 'updated successfully')
