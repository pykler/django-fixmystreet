from django.conf.urls.defaults import *
from django.conf import settings
from django.http import HttpResponseRedirect
from django.contrib import admin
from mainapp.feeds import LatestReports, LatestReportsByCity, LatestReportsByWard, LatestUpdatesByReport
from contrib.django_restapi.responder import JSONResponder

# models
from mainapp.models import Report, ReportJSON


feeds = {
    'reports': LatestReports,
    'wards': LatestReportsByWard,
    'cities': LatestReportsByCity,
    'report_updates': LatestUpdatesByReport,
}

admin.autodiscover()
urlpatterns = patterns('',
    (r'^admin/(.*)', admin.site.root),
    (r'^feeds/(?P<url>.*)/$', 'django.contrib.syndication.views.feed', {'feed_dict': feeds}),
    (r'^i18n/', include('django.conf.urls.i18n')),
)


urlpatterns += patterns('mainapp.views.main',
    (r'^$', 'index'),
    (r'^search', 'search_address'),
    (r'about/$', 'about')
)

urlpatterns += patterns('mainapp.views.faq',
    (r'^about/(\S+)$', 'show'),
)


urlpatterns += patterns('mainapp.views.promotion',
    (r'^promotions/(\w+)$', 'show'),
)


urlpatterns += patterns('mainapp.views.wards',
    (r'^wards/(\d+)', 'show'),       
    (r'^cities/(\d+)/wards/(\d+)', 'show_by_number'),       
    
)

urlpatterns += patterns('mainapp.views.cities',
    (r'^cities/(\d+)$', 'show'),       
    (r'^cities', 'index'),
)

urlpatterns += patterns( 'mainapp.views.reports.updates',
    (r'^reports/updates/confirm/(\S+)', 'confirm'), 
    (r'^reports/updates/create/', 'create'), 
    (r'^reports/(\d+)/updates/', 'new'),
)


urlpatterns += patterns( 'mainapp.views.reports.subscribers',
    (r'^reports/subscribers/confirm/(\S+)', 'confirm'), 
    (r'^reports/subscribers/unsubscribe/(\S+)', 'unsubscribe'),
    (r'^reports/subscribers/create/', 'create'),
    (r'^reports/(\d+)/subscribers', 'new'),
)

urlpatterns += patterns( 'mainapp.views.reports.flags',
    (r'^reports/(\d+)/flags/thanks', 'thanks'),
    (r'^reports/(\d+)/flags', 'new'),
)

urlpatterns += patterns('mainapp.views.reports.main',
    (r'^reports/(\d+)$', 'show'),       
    (r'^reports/', 'new'),
)

urlpatterns += patterns('mainapp.views.contact',
    (r'^contact/thanks', 'thanks'),
    (r'^contact', 'new'),
)

urlpatterns += patterns('mainapp.views.ajax',
    (r'^ajax/categories/(\d+)', 'category_desc'),
)

# REST
json_report_resource = ReportJSON(
    queryset=Report.objects.all(),
    permitted_methods = ('GET', 'POST'),
#     expose_fields = ('id','point'),
    responder = JSONResponder()
#     responder = JSONResponder(paginate_by = 2)
)

urlpatterns += patterns('',
   url(r'^json/report/?$', json_report_resource),
)


#The following is used to serve up local media files like images
if settings.LOCAL_DEV:
    baseurlregex = r'^media/(?P<path>.*)$'
    urlpatterns += patterns('',
        (baseurlregex, 'django.views.static.serve',
        {'document_root':  settings.MEDIA_ROOT}),
    )
