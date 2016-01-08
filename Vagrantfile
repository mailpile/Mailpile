# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|

  config.vm.box     = 'bento/debian-8.2'

  config.vm.provider "virtualbox" do |v|
    v.customize ["modifyvm", :id, "--memory", 1024]
  end

  config.vm.synced_folder '.', '/srv/Mailpile'
  config.vm.network :forwarded_port, guest: 33411, host: 33411
  config.vm.network :forwarded_port, guest: 8888, host: 8888
  config.vm.provision :shell, :path => 'scripts/vagrant_bootstrap.sh'
end
