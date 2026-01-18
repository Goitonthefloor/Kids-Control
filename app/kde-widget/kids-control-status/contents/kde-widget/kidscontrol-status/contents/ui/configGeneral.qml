import QtQuick 2.15
import QtQuick.Layouts 1.15
import org.kde.plasma.components 3.0 as PC3

Item {
    width: 400
    height: 240

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        PC3.Label {
            text: "Server-URL"
        }
        PC3.TextField {
            Layout.fillWidth: true
            text: plasmoid.configuration.serverUrl
            placeholderText: "http://localhost:8000/api/widget/status"
            onTextChanged: plasmoid.configuration.serverUrl = text.trim()
        }

        PC3.Label {
            text: "Widget-Token (optional)"
        }
        PC3.TextField {
            Layout.fillWidth: true
            text: plasmoid.configuration.token
            placeholderText: "KIDSCONTROL_WIDGET_TOKEN"
            echoMode: TextInput.Password
            onTextChanged: plasmoid.configuration.token = text
        }

        PC3.Label {
            text: "Aktualisierung (Sekunden)"
        }
        PC3.SpinBox {
            Layout.fillWidth: true
            from: 5
            to: 600
            value: plasmoid.configuration.refreshSeconds
            onValueChanged: plasmoid.configuration.refreshSeconds = value
        }
    }
}
