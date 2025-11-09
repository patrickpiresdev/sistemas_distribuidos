# Multicast Chat App

This is a simple multicast chat application implemented in Python. It allows multiple peers to join a multicast group and exchange messages.

## TODO

- [X] network admission
- [ ] coordinator management
    - [X] assign unique IDs to new members
    - [X] notify all members of new additions
    - [X] send heartbeats to inform that coordinator is alive and send updated state in case some information was missed along the way (because of packet loss in UDP)
    - [ ] notify members when someone leaves the group
    - [ ] identify coordinator failure based on missing heartbeats
    - [ ] enter election process when coordinator failure is detected
    - [ ] implement election algorithm to choose new coordinator in case the current one goes down: bully or ring
    - [ ] notify members when a new coordinator is elected
- [ ] consistent chat history
    - all nodes should have the same chat history
- [ ] take care of race conditions
- [ ] improve logging
- [ ] improve ui
