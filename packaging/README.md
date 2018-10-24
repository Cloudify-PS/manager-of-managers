# Creating plugin wagons

In order to manually create a wagon for either the `cmom` or the `meta` plugin,
run the following commands (*in the current folder*) using docker:

```
# This will create a docker image
docker build -t wagon_builder .

# <PATH TO PLUGIN DIR> - absolute path to the plugin dir 
# (e.g. ~/dev/repos/manager-of-managers/plugins/cmom)
# <OUTPUT DIR> - the folder into which the wagon file will be created (e.g /tmp)
docker run --rm -v <PATH TO PLUGIN DIR>:/plugin -v <OUTPUT DIR>:/artifacts wagon_builder
```

Following this, a new `wgn` will be created in `<OUTPUT DIR>`.

> Running the `docker build` command is only necessary the first time. Any subsequent
> runs need only the `docker run` command.