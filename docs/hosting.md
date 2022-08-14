
# Meld hosting infrastructure


## Hosting

* DNS is hosted by Cloudflare
* SSL/TLS is handled by Cloudflare
* Website is served by Cloudflare Workers
* Windows binaries are hosted on the GNOME FTP server mirrors
* Other package options, including Flatpak releases, are built and hosted by
  external providers

Note that the Cloudflare site runs on a private account.


## Build

Site build runs on GNOME Gitlab CI, first building the site and publishing to
Gitlab pages, and then deploying the built static site to Cloudflare. See
`.gitlab-ci.yml` in the `pages` Git branch for details.


## DNS

* meldmerge.org - the main Meld website domain since 2011
* meld.app - new/secondary website domain, first actually used in 2021

Both domains are privately registered.


## Infrastructure TODO list (August 2022)

* Automate CI release tarball uploads
* Automate CI release MSI uploads
* Set release branches to protected if possible; this might not be possible if
  it will interfere with the GNOME translation team's workflow
