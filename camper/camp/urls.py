from django.conf.urls import patterns, include, url


urlpatterns = patterns(
    'camper.camp.views',
    url(r'^subscribe/$', 'email_subscribe', name="create_email_subscriber"),
)
