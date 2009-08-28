from contrib.django_restapi.model_resource import Collection
from contrib.django_restapi.responder import JSONResponder
from django.contrib.gis.geos import fromstr 
from django.contrib.gis.measure import D

from mainapp.models import Report

class ReportJSON(Collection):

    def read(self, request):
        lon = request.GET["lon"]
        lat = request.GET["lat"]
        radius = float(request.GET.get('r', 4))
        point_str = "POINT(%s %s)" %(lon, lat)
        pnt = fromstr(point_str, srid=4326)
        reports = Report.objects.filter(is_confirmed = True,point__distance_lte=(pnt,D(km=radius))).distance(pnt).order_by('distance')
        return self.responder.list(request, reports)

reports_resource = ReportJSON(
    queryset=Report.objects.all(),
    permitted_methods = ('GET', 'POST'),
#     expose_fields = ('id','point'),
    responder = JSONResponder()
#     responder = JSONResponder(paginate_by = 2)
)
