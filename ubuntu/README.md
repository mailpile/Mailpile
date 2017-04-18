## Desktop Menu-Entry & Upstart file

    sudo cp -i ubuntu/mailpile.conf /etc/init/
    cp ubuntu/mailpile.desktop ~/.local/share/applications/
    cp default-theme/img/logo-color.png ~/.icons/mailpile.png
    sudo ln -s $(pwd)/scripts/mailpile /usr/local/bin/mailpile

    sudo adduser mailpile --disabled-password
    sudo usermod -L mailpile
    sudo chown -R mailpile:mailpile .

    sudo initctl reload-configuration
    sudo initctl start mailpile
