import UIKit
import WebKit

final class ViewController: UIViewController, WKScriptMessageHandler {
    private var webView: WKWebView!

    override var preferredStatusBarStyle: UIStatusBarStyle {
        .lightContent
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 7/255, green: 13/255, blue: 20/255, alpha: 1)

        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.userContentController.add(self, name: "haptic")

        webView = WKWebView(frame: view.bounds, configuration: config)
        webView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        webView.isOpaque = false
        webView.backgroundColor = view.backgroundColor
        webView.scrollView.bounces = false
        webView.scrollView.isScrollEnabled = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        view.addSubview(webView)

        if let indexURL = Bundle.main.url(forResource: "index", withExtension: "html", subdirectory: "www") {
            let wwwDir = indexURL.deletingLastPathComponent()
            webView.loadFileURL(indexURL, allowingReadAccessTo: wwwDir)
        } else {
            webView.loadHTMLString("<h1>Missing www/index.html</h1>", baseURL: nil)
        }
    }

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard message.name == "haptic", let style = message.body as? String else { return }
        let feedbackStyle: UIImpactFeedbackGenerator.FeedbackStyle
        switch style {
        case "heavy":
            feedbackStyle = .heavy
        case "medium":
            feedbackStyle = .medium
        default:
            feedbackStyle = .light
        }
        let gen = UIImpactFeedbackGenerator(style: feedbackStyle)
        gen.prepare()
        gen.impactOccurred()
    }
}
