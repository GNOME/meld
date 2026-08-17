from unittest import mock

from gi.repository import Gio

with mock.patch("gi._gtktemplate.validate_resource_path", mock.Mock(return_value=True)):
    from meld.imagediff import file_is_image


def test_local_image_detection_uses_gdkpixbuf():
    gfile = mock.Mock()
    gfile.get_path.return_value = "C:\\images\\image.png"

    with mock.patch(
        "meld.imagediff.GdkPixbuf.Pixbuf.get_file_info",
        return_value=(mock.Mock(), 100, 100),
    ) as get_file_info:
        assert file_is_image(gfile)

    get_file_info.assert_called_once_with("C:\\images\\image.png")
    gfile.query_info.assert_not_called()


def test_local_non_image_detection_uses_gdkpixbuf():
    gfile = mock.Mock()
    gfile.get_path.return_value = "C:\\documents\\notes.txt"

    with mock.patch(
        "meld.imagediff.GdkPixbuf.Pixbuf.get_file_info",
        return_value=(None, 0, 0),
    ):
        assert not file_is_image(gfile)

    gfile.query_info.assert_not_called()


def test_uri_image_detection_uses_gio_content_type():
    gfile = mock.Mock()
    gfile.get_path.return_value = None
    file_info = mock.Mock()
    file_info.get_content_type.return_value = "image/png"
    gfile.query_info.return_value = file_info

    with (
        mock.patch(
            "meld.imagediff.get_supported_image_mime_types",
            return_value=("image/png",),
        ),
        mock.patch("meld.imagediff.GdkPixbuf.Pixbuf.get_file_info") as get_file_info,
    ):
        assert file_is_image(gfile)

    get_file_info.assert_not_called()
    gfile.query_info.assert_called_once_with(
        Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
        Gio.FileQueryInfoFlags.NONE,
        None,
    )
