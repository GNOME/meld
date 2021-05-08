
Meld website
============

This branch exists to keep and build Meld's website.


Build
-----

The build process (see `.gitlab-ci.yml`) has three stages. The first stage
builds the actual site using Jekyll, outputting to the `public` folder. The
second stage switches to the master branch and uses the Yelp build tool to
generate an HTML version of Meld's help, which is output to a `help` subfolder
under the existing `public` folder. This public folder is the artifact that is
then uploaded to the GitLab Pages site.

In order to make the page more easily accessible, and to retain our current
well-known domain, this site is then published to Cloudflare workers.


Screenshots
-----------

These have been minimized using `pngquant` (https://pngquant.org/), since
absolute lossless presentation isn't really necessary here, and the size
saving is significant.
