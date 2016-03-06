from django.conf.urls import patterns, url

urlpatterns = patterns('camper.sms.views',
    # url(r'^$', 'tcamp.views.home', name='home'),
    url(r'^$', 'coming_up'),
)
