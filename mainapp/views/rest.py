from contrib.django_restapi.model_resource import Collection
from contrib.django_restapi.responder import JSONResponder, XMLResponder
from django.contrib.gis.geos import fromstr
from django.contrib.gis.measure import D
from django.forms.util import ErrorDict

from mainapp.models import Report


class RestCollection(Collection):
    ''' Subclasses Collection to provide multiple responders '''
    def __init__(self, queryset, responders=None, **kwargs):
        '''
        Replaces the responder in Collection.__init__ with responders, which
        maybe a list of responders or None. In the case of None, default
        responders are allocated to the colelction.

        See Collection.__init__ for more details
        '''
        if responders is None:
            responders = {
                'json'  : JSONResponder(),
                'xml'   :XMLResponder(),
            }
        self.responders = {}
        for k, r in responders.items():
            Collection.__init__(self, queryset, r, **kwargs)
            self.responders[k] = self.responder

    def __call__(self, request, format, *args, **kwargs):
        '''
        urls.py must contain .(?P<format>\w+) at the end of the url
        for rest resources, such that it would match one of the keys
        in self.responders
        '''
        if format in self.responders:
            self.responder = self.responders[format]
            return Collection.__call__(self, request, *args, **kwargs)
        errors = ErrorDict(
            {'info': ['Requested content type "%s" not available!' %format]})
        # Using the last used responder to reutrn a 415
        return self.responder.error(request, 415, errors)


class ReportRest(RestCollection):

    def read(self, request):
        lon = request.GET["lon"]
        lat = request.GET["lat"]
        radius = float(request.GET.get('r', 4))
        point_str = "POINT(%s %s)" %(lon, lat)
        pnt = fromstr(point_str, srid=4326)
        reports = Report.objects.filter(is_confirmed = True,point__distance_lte=(pnt,D(km=radius))).distance(pnt).order_by('distance')
        return self.responder.list(request, reports)

reports_rest = ReportRest(
    queryset=Report.objects.all(),
    permitted_methods = ('GET', 'POST'),
#     expose_fields = ('id','point'),
)
