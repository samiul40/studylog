from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    priority = 1.0
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return ["index", "account_signup", "account_login"]

    def location(self, item):
        return reverse(item)
