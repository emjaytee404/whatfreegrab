WhatFreeGrab
===

WhatFreeGrab is an automated freeleech grabber for What.CD.

Tell me more
---

WhatFreeGrab is a Python script to automatically download freeleech torrents
from What.CD.

The only dependencies outside the standard library are the [requests](#credits) and [whatapi](#credits) modules, and both can be downloaded by the script during the setup stage.

Credits
---

WhatFreeGrab borrows heavily from [Yoink!](https://github.com/phracker/yoink) by phracker, using code
originally by tobbez, and from [whatapi](https://github.com/isaaczafuta/whatapi) by isaaczafuta. Many thanks.

Installation:
---

~~~
git clone https://github.com/emjaytee404/whatfreegrab.git
cd whatfreegrab
~~~

Now use this command to run the setup wizard and follow the prompts:

~~~
python WFG-setup.py
~~~

Configuration
---

### Template Fields

The filename template is created using data fields available for each torrent.

The default values are:

~~~
template_music =  ${artist} - ${groupName} (${format} ${encoding}) [${torrentId}]
template_other =  ${groupName} [${torrentId}]
~~~

To match the Yoink! style filenames, set your naming templates like so:

~~~
template_music = ${torrentId}. ${yoinkFormat}
template_music = ${torrentId} ${yoinkFormat}
~~~

**Note:** that values outside of the defaults are untested.

### Fields

For music torrents, the following fields are available:

`artist` `artists` `bookmarked` `canUseToken` `cover` `editionId` `encoding` `fileCount`
`format` `groupId` `groupName` `groupTime` `groupYear` `hasCue` `hasLog` `hasSnatched`
`isFreeleech` `isNeutralLeech` `isPersonalFreeleech` `leechers` `logScore` `maxSize`
`media` `releaseType` `remasterCatalogueNumber` `remasterTitle` `remasterYear`
`remastered` `scene` `seeders` `size` `snatches` `tags` `time` `torrentId`
`totalLeechers` `totalSeeders` `totalSnatched` `vanityHouse`

For non-music torrents, the following fields are available:

`canUseToken` `category` `fileCount` `groupId` `groupName` `groupTime` `hasSnatched`
`isFreeleech` `isNeutralLeech` `isPersonalFreeleech` `leechers` `seeders` `size`
`snatches` `tags` `torrentId`