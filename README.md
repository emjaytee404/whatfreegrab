WhatFreeGrab?
---

*An automated freeleech grabber for What.CD*

WhatFreeGrab? is a Python script to automatically download freeleech torrents
from What.CD.

The only dependency outside the standard library is the requests module, and
that can be downloaded by the script as well.

Edit the wfg.cfg file with your WCD username, password and the target directory
where you want the torrents saved.

Credits
---

WhatFreeGrab borrows heavily from Yoink! [1], by phracker, using code
originally by tobbez, and from whatapi [2] by isaaczafuta. Many thanks.

1. [https://github.com/phracker/yoink](https://github.com/phracker/yoink)
1. [https://github.com/isaaczafuta/whatapi](https://github.com/isaaczafuta/whatapi)

Template Fields
---

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