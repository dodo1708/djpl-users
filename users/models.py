# -*- coding: utf-8 -*-
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import ugettext as _
from emailing.emails import HtmlEmail


class AbstractUser(User):
    '''
    Defines an abstract user model which can be inherited and refined by a concrete application's user
    model.
    '''

    def __init__(self, *args, **kwargs):
        super(AbstractUser, self).__init__(*args, **kwargs)
        # make the email field (inherited from User) mandatory
        self._meta.get_field_by_name('email')[0].null = False
        self._meta.get_field_by_name('email')[0].blank = False
        self._meta.get_field_by_name('username')[0].max_length = 300  # FIXME: does not work on syncdb on postgres

    class Meta:
        abstract = True

    def __unicode__(self):
        return self.username

    def save(self, send_confirmation=True):
        updated = self.id

        if not updated:
            # set unusable password before the user is saved
            self.set_unusable_password()
            self.is_staff = self.appconfig.IS_STAFF

        super(AbstractUser, self).save()

        if not updated and self.is_active and send_confirmation:
            # send account confirmation mail after user was saved
            self.confirm_account()

    def confirm_account(self, template='users/email/account_confirmation.html', extra_context={}, subject=None):
        '''
        Sends out an account confirm email. Which contains a link to set the user's password.
        This method is also used for the password_reset mechanism.
        '''
        conf = self.appconfig
        bcc = settings.ADDITIONALLY_SEND_TO
        subject = subject or conf.CONFIRM_EMAIL_SUBJECT

        if settings.IGNORE_USER_EMAIL:
            receipients = bcc
            bcc = None
        else:
            receipients = [self.email]

        token = default_token_generator.make_token(self)

        context = {
            'user': self,
            'password_reset_confirm_url': self.get_confirm_link(self.urlnames.password_reset_confirm_urlname, token),
            'account_confirm_url': self.get_confirm_link(self.urlnames.account_confirm_urlname, token),
            'login_url': self._get_domain() + settings.LOGIN_URL
        }
        context.update(extra_context)

        email = HtmlEmail(
            from_email=conf.FROM_EMAIL,
            to=receipients,
            bcc=bcc,
            subject=subject,
            template=template,
            context=context
        )
        email.send()

    def get_confirm_link(self, urlname, token):
        return '%s%s' % (
            self._get_domain(),
            reverse(urlname, kwargs={
                'uidb64': urlsafe_base64_encode(force_bytes(self.id)),
                'token': token
            })
        )

    def _get_domain(self):
        domain = Site.objects.get(id=settings.SITE_ID).domain
        if not domain.startswith('http'):
            domain = 'http://' + domain
        return domain

    def full_name(self):
        return '%s %s' % (self.first_name, self.last_name)

    def clean(self):
        qs = User.objects.filter(username=self.email)
        if self.id:
            u = User.objects.get(id=self.id)
            qs = qs.exclude(email=u.email)
        if qs.count() > 0:
            raise ValidationError(_('Ein Benutzer mit dieser Email-Adresse existiert bereits.'))
