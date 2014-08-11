return {
    activity_setup: function() {
        $(".plugin-activity-i18nhelper").click(function() {
            Mailpile.API.i18n_recent_get({}, function(data) {
                console.log(data);
                var rows = "";
                for (key in data.result) {
                    value = data.result[key];
                    rows += "<tr><td>" + key + "</td><td>" + value + "</td></tr>";
                }
                $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
                $('#modal-full .modal-header').append("Recently Translated Strings");
                $('#modal-full .modal-body').html(
                  "<table>"
                + "<tr><th>Original string</th><th>Translated string</th></tr>"
                + rows
                + "</table>");
            });
        });
    }
};
