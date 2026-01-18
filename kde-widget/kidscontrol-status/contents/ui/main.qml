import QtQuick 2.15
import QtQuick.Layouts 1.15
import org.kde.plasma.components 3.0 as PC3
import org.kde.plasma.core 2.0 as PlasmaCore

Item {
    id: root
    width: 380
    height: 320

    property var kids: []
    property string serverTime: ""
    property string errorMessage: ""
    property bool loading: false

    function buildUrl() {
        var baseUrl = plasmoid.configuration.serverUrl || "";
        if (!baseUrl.length) {
            return "";
        }
        var token = plasmoid.configuration.token || "";
        if (!token.length) {
            return baseUrl;
        }
        var sep = baseUrl.indexOf("?") === -1 ? "?" : "&";
        return baseUrl + sep + "t=" + encodeURIComponent(token);
    }

    function refresh() {
        var url = buildUrl();
        if (!url.length) {
            errorMessage = "Server-URL fehlt.";
            kids = [];
            return;
        }
        loading = true;
        errorMessage = "";

        var xhr = new XMLHttpRequest();
        xhr.open("GET", url);
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== XMLHttpRequest.DONE) {
                return;
            }
            loading = false;
            if (xhr.status !== 200) {
                errorMessage = "Fehler: " + xhr.status;
                kids = [];
                return;
            }
            try {
                var data = JSON.parse(xhr.responseText);
                kids = data.kids || [];
                serverTime = data.server_time || "";
            } catch (err) {
                errorMessage = "Antwort ungültig.";
                kids = [];
            }
        };
        xhr.send();
    }

    Timer {
        id: poller
        interval: Math.max(5, plasmoid.configuration.refreshSeconds || 30) * 1000
        repeat: true
        running: true
        onTriggered: refresh()
    }

    Component.onCompleted: refresh()

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            PC3.Label {
                text: "Kids-Control"
                font.bold: true
                Layout.fillWidth: true
            }

            PC3.Button {
                text: loading ? "…" : "↻"
                enabled: !loading
                onClicked: refresh()
            }
        }

        PC3.Label {
            Layout.fillWidth: true
            text: serverTime.length ? ("Serverzeit: " + serverTime) : ""
            color: PlasmaCore.Theme.disabledTextColor
            font.pixelSize: 11
            visible: serverTime.length
        }

        PC3.Label {
            Layout.fillWidth: true
            text: errorMessage
            color: PlasmaCore.Theme.negativeTextColor
            visible: errorMessage.length
        }

        PC3.ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: listView
                anchors.fill: parent
                model: kids
                spacing: 10
                clip: true

                delegate: PC3.Frame {
                    width: listView.width

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true

                            PC3.Label {
                                text: model.display_name || model.username
                                font.bold: true
                                Layout.fillWidth: true
                            }

                            PC3.Label {
                                text: model.allow ? "✅" : "⛔"
                            }

                            PC3.Label {
                                text: model.warn ? "⚠️" : ""
                                visible: model.warn
                            }
                        }

                        PC3.Label {
                            Layout.fillWidth: true
                            text: model.allow ? "Erlaubt" : "Gesperrt"
                            color: model.allow ? PlasmaCore.Theme.positiveTextColor : PlasmaCore.Theme.negativeTextColor
                        }

                        PC3.Label {
                            Layout.fillWidth: true
                            text: model.reason_label || model.reason
                            color: PlasmaCore.Theme.disabledTextColor
                            font.pixelSize: 11
                            visible: (model.reason_label || model.reason)
                        }

                        PC3.Label {
                            Layout.fillWidth: true
                            text: model.remaining_label ? ("Rest: " + model.remaining_label) : "Rest: —"
                            font.pixelSize: 11
                        }
                    }
                }
            }
        }
    }
}
