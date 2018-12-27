#!/bin/bash

chmod 400 $HOME/ssh_key
unset LOCAL_REST_CERT_FILE

function wait_for_cfy() {
  for i in {1..10};
  do
    cfy blueprints list
    if [[ $? != 0 ]];
    then
      sleep 5;
    else
      return;
    fi
  done
}

function setup_patchify()
{
  sudo yum install -y patch git
  pushd $HOME
  git clone https://github.com/cloudify-cosmo/patchify.git

}

function patch_cluster_member()
{
  pushd $HOME/patchify
  git apply --stat $HOME/0001-skip-host-checking-on-patchify.patch
  git apply --check $HOME/0001-skip-host-checking-on-patchify.patch
  git am --signoff < $HOME/0001-skip-host-checking-on-patchify.patch
  ./patchify -p 4.5_make_validate_agent_recover.json -c centos@localhost -i $HOME/ssh_key || true
}

setup_patchify
wait_for_cfy
patch_cluster_member
